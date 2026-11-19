
import os
import secrets
import json
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from fastapi.responses import FileResponse

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    UploadFile,
    File
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from bson import ObjectId
from jose import jwt, JWTError

from email_service import send_interview_email

from database import (
    users_collection,
    jobs_collection,
    applications_collection,
    resumes_collection,
    interviews_collection,
    notifications_collection,
    assistant_conversations_collection
)

# =========================================
# ROUTER CONFIGURATION
# =========================================

router = APIRouter()

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "campusconnect_change_this_to_a_long_random_secret_key"
)

ALGORITHM = "HS256"

security = HTTPBearer()

BASE_DIR = Path(__file__).resolve().parent

RESUME_DIR = BASE_DIR / "uploads" / "resumes"

RESUME_DIR.mkdir(parents=True, exist_ok=True)

MAX_RESUME_SIZE = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}


# =========================================
# AUTHENTICATION
# =========================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if not user_id or not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token."
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token."
        )

    user = users_collection.find_one({
        "_id": ObjectId(user_id)
    })

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found."
        )

    return {
        "user_id": str(user["_id"]),
        "name": user.get("full_name"),
        "email": user.get("email"),
        "role": user.get("role")
    }


def require_role(user, roles):
    if user["role"] not in roles:
        raise HTTPException(
            status_code=403,
            detail="Access denied."
        )


def create_notification(user_id, title, message, category):
    notifications_collection.insert_one({
        "user_id": ObjectId(user_id),
        "title": title,
        "message": message,
        "category": category,
        "is_read": False,
        "created_at": datetime.now(timezone.utc)
    })


def serialize_notification(notification):
    created_at = notification.get("created_at")

    return {
        "id": str(notification["_id"]),
        "title": notification.get("title"),
        "message": notification.get("message"),
        "category": notification.get("category"),
        "is_read": notification.get("is_read", False),
        "created_at": (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else created_at
        )
    }


# =========================================
# INTERVIEW REQUEST MODEL
# =========================================

class InterviewCreate(BaseModel):
    application_id: str
    scheduled_at: datetime
    interview_mode: str = "Online"
    meeting_link: str = ""
    location: str = ""
    notes: str = ""


# =========================================
# RESUME UPLOAD
# =========================================

@router.post("/students/resume")
async def upload_resume(
    resume: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["student"])

    extension = Path(resume.filename or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOC and DOCX resumes are allowed."
        )

    content = await resume.read(MAX_RESUME_SIZE + 1)

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The uploaded resume is empty."
        )

    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Resume size must not exceed 5 MB."
        )

    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file."
        )

    student_id = ObjectId(current_user["user_id"])

    filename = secrets.token_hex(16) + extension

    file_path = RESUME_DIR / filename

    try:
        with open(file_path, "wb") as file:
            file.write(content)

        existing_resume = resumes_collection.find_one({
            "student_id": student_id
        })

        resume_data = {
            "student_id": student_id,
            "filename": resume.filename,
            "stored_filename": filename,
            "file_path": str(file_path),
            "file_size": len(content),
            "uploaded_at": datetime.now(timezone.utc)
        }

        if existing_resume:
            old_file = existing_resume.get("file_path")

            resumes_collection.update_one(
                {"_id": existing_resume["_id"]},
                {"$set": resume_data}
            )

            if old_file and Path(old_file).is_file():
                Path(old_file).unlink()

        else:
            resumes_collection.insert_one(resume_data)

    except Exception:
        if file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=500,
            detail="Unable to save resume."
        )

    return {
        "message": "Resume uploaded successfully.",
        "filename": resume.filename,
        "size": len(content)
    }


# =========================================
# VIEW OWN RESUME DETAILS
# =========================================

@router.get("/students/resume")
def get_student_resume(
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["student"])

    resume = resumes_collection.find_one({
        "student_id": ObjectId(current_user["user_id"])
    })

    if not resume:
        return {
            "uploaded": False,
            "message": "No resume uploaded."
        }

    uploaded_at = resume.get("uploaded_at")

    return {
        "uploaded": True,
        "filename": resume.get("filename"),
        "file_size": resume.get("file_size"),
        "uploaded_at": (
            uploaded_at.isoformat()
            if isinstance(uploaded_at, datetime)
            else uploaded_at
        )
    }


# =========================================
# RECRUITER - VIEW APPLICANT RESUME
# =========================================

@router.get("/recruiter/applications/{application_id}/resume")
def get_applicant_resume(
    application_id: str,
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["recruiter"])

    if not ObjectId.is_valid(application_id):
        raise HTTPException(status_code=400, detail="Invalid application ID.")

    application = applications_collection.find_one({
        "_id": ObjectId(application_id)
    })

    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")

    job_id = application.get("job_id")

    if not isinstance(job_id, ObjectId):
        if not ObjectId.is_valid(str(job_id)):
            raise HTTPException(status_code=400, detail="Invalid job ID.")
        job_id = ObjectId(str(job_id))

    job = jobs_collection.find_one({"_id": job_id})

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if str(job.get("recruiter_id")) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    resume = resumes_collection.find_one({
        "student_id": application["student_id"]
    })

    if not resume:
        raise HTTPException(
            status_code=404,
            detail="Student has not uploaded a resume."
        )

    file_path = Path(resume.get("file_path", ""))

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Resume file not found.")

    extension = file_path.suffix.lower()

    media_types = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }

    return FileResponse(
        path=str(file_path),
        media_type=media_types.get(extension, "application/octet-stream"),
        filename=resume.get("filename", "resume"),
        content_disposition_type="inline"
    )


# =========================================
# RECRUITER APPLICATION PICKER (NO MANUAL ID ENTRY)
# =========================================

@router.get("/recruiters/me/applications")
def recruiter_application_options(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["recruiter"])
    recruiter_oid = ObjectId(current_user["user_id"])
    recruiter_jobs = list(jobs_collection.find({"recruiter_id": recruiter_oid}))
    job_map = {str(job["_id"]): job for job in recruiter_jobs}
    if not job_map:
        return []
    applications = applications_collection.find(
        {"job_id": {"$in": [job["_id"] for job in recruiter_jobs]}}
    ).sort("applied_at", -1)
    options = []
    for application in applications:
        student = users_collection.find_one({"_id": application.get("student_id")}) or {}
        job = job_map.get(str(application.get("job_id")), {})
        application_code = application.get("application_code") or f"APP-{int(str(application['_id'])[-6:], 16):06d}"
        if not application.get("application_code"):
            applications_collection.update_one(
                {"_id": application["_id"]},
                {"$set": {"application_code": application_code}},
            )
        options.append({
            "application_id": str(application["_id"]),
            "application_code": application_code,
            "student_name": student.get("full_name", "Student"),
            "student_code": student.get("student_code", ""),
            "student_email": student.get("email", ""),
            "job_title": job.get("job_title", job.get("title", "Position")),
            "company_name": job.get("company_name", job.get("company", "Company")),
            "status": application.get("status", "Applied"),
            "applied_at": application.get("applied_at").isoformat() if isinstance(application.get("applied_at"), datetime) else None,
        })
    return options


# =========================================
# SCHEDULE INTERVIEW
# =========================================

@router.post("/interviews")
def schedule_interview(
    interview: InterviewCreate,
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["recruiter"])

    supplied_reference = interview.application_id.strip()
    if supplied_reference.upper().startswith("APP-"):
        application = applications_collection.find_one({
            "application_code": supplied_reference.upper()
        })
    elif ObjectId.is_valid(supplied_reference):
        application = applications_collection.find_one({
            "_id": ObjectId(supplied_reference)
        })
    else:
        application = None

    if application and not application.get("application_code"):
        application_code = f"APP-{int(str(application['_id'])[-6:], 16):06d}"
        applications_collection.update_one(
            {"_id": application["_id"]},
            {"$set": {"application_code": application_code}},
        )

    if not application:
        raise HTTPException(
            status_code=404,
            detail="Application not found."
        )

    job_id = application.get("job_id")

    if not isinstance(job_id, ObjectId):
        if not ObjectId.is_valid(str(job_id)):
            raise HTTPException(
                status_code=400,
                detail="Invalid job reference."
            )

        job_id = ObjectId(str(job_id))

    job = jobs_collection.find_one({
        "_id": job_id
    })

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found."
        )

    recruiter_id = job.get("recruiter_id")

    if str(recruiter_id) != current_user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail="You cannot schedule interviews for another recruiter's job."
        )

    scheduled_at = interview.scheduled_at

    if scheduled_at.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="Interview date must include a timezone."
        )

    scheduled_at = scheduled_at.astimezone(timezone.utc)

    if scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Interview must be scheduled in the future."
        )

    if interview.interview_mode not in ["Online", "Offline"]:
        raise HTTPException(
            status_code=400,
            detail="Interview mode must be Online or Offline."
        )

    if interview.interview_mode == "Online" and not interview.meeting_link:
        raise HTTPException(
            status_code=400,
            detail="Meeting link is required for online interviews."
        )

    if interview.interview_mode == "Offline" and not interview.location:
        raise HTTPException(
            status_code=400,
            detail="Interview location is required for offline interviews."
        )

    interview_data = {
        "application_id": ObjectId(interview.application_id),
        "student_id": application["student_id"],
        "recruiter_id": ObjectId(current_user["user_id"]),
        "job_id": job_id,
        "scheduled_at": scheduled_at,
        "interview_mode": interview.interview_mode,
        "meeting_link": interview.meeting_link,
        "location": interview.location,
        "notes": interview.notes,
        "status": "Scheduled",
        "created_at": datetime.now(timezone.utc)
    }

    result = interviews_collection.insert_one(interview_data)

    applications_collection.update_one(
        {"_id": application["_id"]},
        {
            "$set": {
                "status": "Interview Scheduled",
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    create_notification(
        str(application["student_id"]),
        "Interview Scheduled",
        "Your interview has been scheduled. Please check your interview details.",
        "interview"
    )

    # Send interview email without interrupting scheduling
    # if SMTP is unavailable or not configured.

    try:
        student = users_collection.find_one({
            "_id": application["student_id"]
        })

        if student and student.get("email"):
            send_interview_email(
                student.get("full_name", "Student"),
                student["email"],
                job.get("job_title", job.get("title", "")),
                job.get("company_name", job.get("company", "")),
                scheduled_at.isoformat(),
                interview.interview_mode,
                interview.meeting_link
            )

    except Exception as email_error:
        print("Interview email notification failed:", email_error)

    return {
        "message": "Interview scheduled successfully.",
        "interview_id": str(result.inserted_id)
    }


# =========================================
# VIEW STUDENT INTERVIEWS
# =========================================

@router.get("/students/{student_id}/interviews")
def get_student_interviews(
    student_id: str,
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["student"])

    if current_user["user_id"] != student_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied."
        )

    interviews = interviews_collection.find({
        "student_id": ObjectId(student_id)
    }).sort("scheduled_at", 1)

    results = []

    for item in interviews:

        job = jobs_collection.find_one({
            "_id": item.get("job_id")
        })

        results.append({
            "id": str(item["_id"]),
            "application_id": str(item["application_id"]),

            "job_title": (
                job.get("job_title", job.get("title", ""))
                if job else ""
            ),

            "company_name": (
                job.get("company_name", job.get("company", ""))
                if job else ""
            ),

            "scheduled_at": item["scheduled_at"].isoformat(),
            "interview_mode": item["interview_mode"],
            "meeting_link": item.get("meeting_link", ""),
            "location": item.get("location", ""),
            "notes": item.get("notes", ""),
            "status": item.get("status", "Scheduled")
        })

    return results


# =========================================
# VIEW RECRUITER INTERVIEWS
# =========================================

@router.get("/recruiters/{recruiter_id}/interviews")
def get_recruiter_interviews(
    recruiter_id: str,
    current_user: dict = Depends(get_current_user)
):
    require_role(current_user, ["recruiter"])

    if current_user["user_id"] != recruiter_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied."
        )

    interviews = interviews_collection.find({
        "recruiter_id": ObjectId(recruiter_id)
    }).sort("scheduled_at", 1)

    results = []

    for item in interviews:

        student = users_collection.find_one({
            "_id": item["student_id"]
        })

        job = jobs_collection.find_one({
            "_id": item.get("job_id")
        })

        results.append({
            "id": str(item["_id"]),
            "application_id": str(item["application_id"]),

            "student_name": (
                student.get("full_name", "")
                if student else ""
            ),

            "job_title": (
                job.get("job_title", job.get("title", ""))
                if job else ""
            ),

            "company_name": (
                job.get("company_name", job.get("company", ""))
                if job else ""
            ),

            "scheduled_at": item["scheduled_at"].isoformat(),
            "interview_mode": item["interview_mode"],
            "meeting_link": item.get("meeting_link", ""),
            "location": item.get("location", ""),
            "status": item.get("status", "Scheduled")
        })

    return results


# =========================================
# STUDENT NOTIFICATIONS
# =========================================

@router.get("/notifications")
def get_notifications(
    current_user: dict = Depends(get_current_user)
):
    notifications = notifications_collection.find({
        "user_id": ObjectId(current_user["user_id"])
    }).sort("created_at", -1)

    return [
        serialize_notification(item)
        for item in notifications
    ]


# =========================================
# UNREAD NOTIFICATION COUNT
# =========================================

@router.get("/notifications/unread-count")
def unread_notification_count(
    current_user: dict = Depends(get_current_user)
):
    count = notifications_collection.count_documents({
        "user_id": ObjectId(current_user["user_id"]),
        "is_read": False
    })

    return {
        "unread_count": count
    }


# =========================================
# MARK NOTIFICATION AS READ
# =========================================

@router.put("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    if not ObjectId.is_valid(notification_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid notification ID."
        )

    result = notifications_collection.update_one(
        {
            "_id": ObjectId(notification_id),
            "user_id": ObjectId(current_user["user_id"])
        },
        {
            "$set": {
                "is_read": True,
                "read_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Notification not found."
        )

    return {
        "message": "Notification marked as read."
    }


# =========================================
# CAREERSPHERE AI STUDENT ASSISTANT
# =========================================

class AssistantMessage(BaseModel):
    message: str
    conversation_id: str | None = None
    application_id: str | None = None


def _assistant_fallback(message: str, student: dict, application_context: dict | None = None) -> str:
    """Useful deterministic help when no external AI key is configured."""
    text = message.lower()
    if application_context:
        status = str(application_context.get("status", "Applied"))
        job_title = application_context.get("job_title", "your selected role")
        company = application_context.get("company", "the company")
        stage_guidance = {
            "Applied": "Your application is submitted. Review the job description, practise the listed skills, prepare a role-specific introduction, and keep your resume and contact details current. Watch for recruiter updates.",
            "Shortlisted": "You have been shortlisted. Prepare a 60-second introduction, revise the required technical skills, practise explaining your projects, research the company, and prepare thoughtful questions for the interviewer.",
            "Interview Scheduled": "Your interview is scheduled. Review the date, time, meeting link or venue in My Interviews. Prepare a concise introduction, revise role-specific skills, practise project explanations, and prepare questions for the interviewer.",
            "Selected": "Your application is marked selected. Check your notifications and contact the recruiter or placement office for the official offer, documentation, deadlines and joining instructions.",
            "Rejected": "This application is marked rejected. Review the job requirements, identify skills to strengthen, request constructive feedback if appropriate, and use the experience to prepare for the next opportunity."
        }
        next_steps = stage_guidance.get(status, "Review the latest status in your dashboard and contact the recruiter or placement office if you need clarification.")
        return (f"Application coaching · {job_title} at {company}\nCurrent stage: {status}\n\n{next_steps}\n\nI can guide you through resume alignment, technical preparation, HR questions, mock interviews and a focused preparation plan for this role. I cannot change recruiter decisions or guarantee an outcome.")
    if any(word in text for word in ["resume", "cv"]):
        return (
            "For a stronger placement resume, keep it to one page if you are a fresher. "
            "Use clear sections for education, projects, internships, technical skills, "
            "certifications and achievements. Start bullet points with action verbs and "
            "include measurable outcomes where possible. Upload your latest PDF or DOCX "
            "resume in the Resume section of your student dashboard."
        )
    if any(word in text for word in ["interview", "hr round", "technical round"]):
        return (
            "A practical interview plan: (1) prepare a 60-second introduction, "
            "(2) revise the fundamentals listed in the job description, (3) practise "
            "explaining two projects with your exact contribution, (4) prepare examples "
            "for teamwork and problem-solving, and (5) research the company. Practise "
            "out loud and keep answers structured with Situation, Task, Action and Result."
        )
    if any(word in text for word in ["application", "shortlist", "status"]):
        return (
            "You can track each application in the My Applications section. Statuses "
            "are updated by the recruiter or placement administrator. Check the "
            "notification centre for changes, and make sure your contact details and "
            "resume are current. I cannot change an application status on your behalf."
        )
    if any(word in text for word in ["cgpa", "eligib", "eligible"]):
        return (
            "Check the minimum CGPA, eligible department, graduation year and any "
            "other criteria shown on the job card before applying. Your verified CGPA "
            "is used when academic verification is enabled. If your marksheet is pending, "
            "submit it through Academic Verification and contact your placement office "
            "if the displayed details are incorrect."
        )
    if any(word in text for word in ["prepare", "placement", "roadmap", "study"]):
        return (
            "A balanced placement-preparation routine is: spend time each day on "
            "problem-solving, revise core CS subjects, build and explain one or two "
            "projects, practise communication, and take timed mock interviews. "
            "Use the job description to prioritise topics. Set weekly goals and review "
            "your progress every weekend."
        )
    return (
        f"Hi {student.get('name') or 'there'}! I can help with resume preparation, "
        "interview practice, placement preparation, application tracking and job "
        "eligibility. Ask me a specific question and I will guide you. For live, "
        "AI-generated answers, configure GOOGLE_API_KEY in your environment."
    )


def _generate_assistant_reply(message: str, student: dict, application_context: dict | None = None) -> str:
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return _assistant_fallback(message, student, application_context)

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    prompt = (
        "You are CareerSphere's student placement assistant. Help with resumes, "
        "interviews, placement preparation and understanding this portal. Be clear, "
        "supportive and practical. Never claim to have changed an application or "
        "accessed data that was not supplied. Do not invent company openings, "
        "deadlines, selection results or student records. If asked for live portal "
        "data, direct the student to the relevant dashboard section. Keep answers "
        "concise and structured.\n\n"
        f"Student profile context: name={student.get('name') or 'Student'}, "
        f"department={student.get('department') or 'not supplied'}, "
        f"graduation year={student.get('graduation_year') or 'not supplied'}.\n"
        f"Selected application context: {json.dumps(application_context or {}, default=str)}.\n\n"
        "When an application is selected, guide the student through the current stage, "
        "what that stage means, immediate next actions, preparation tasks, and what to do "
        "if the status changes. Never claim to see unprovided recruiter decisions.\n\n"
        f"Student question: {message}"
    )
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return (
            "I couldn't reach the AI service just now. Please try again in a moment. "
            + _assistant_fallback(message, student, application_context)
        )


@router.post("/assistant/chat")
def assistant_chat(
    payload: AssistantMessage,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["student"])
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Please enter a message.")
    if len(message) > 2000:
        raise HTTPException(status_code=413, detail="Message must be 2,000 characters or fewer.")

    user_id = ObjectId(current_user["user_id"])
    student = users_collection.find_one({"_id": user_id}) or {}
    student_context = {
        "name": student.get("full_name"),
        "department": student.get("department"),
        "graduation_year": student.get("graduation_year"),
    }
    application_context = None
    if payload.application_id:
        if not ObjectId.is_valid(payload.application_id):
            raise HTTPException(status_code=400, detail="Invalid application selection.")
        application = applications_collection.find_one({
            "_id": ObjectId(payload.application_id),
            "student_id": user_id,
        })
        if not application:
            raise HTTPException(status_code=404, detail="That application was not found in your account.")
        job = jobs_collection.find_one({"_id": application.get("job_id")}) or {}
        application_context = {
            "application_id": str(application["_id"]),
            "job_title": job.get("job_title", job.get("title", "Position")),
            "company": job.get("company_name", job.get("company", "Company")),
            "status": application.get("status", "Applied"),
            "applied_at": application.get("applied_at").isoformat() if isinstance(application.get("applied_at"), datetime) else None,
            "minimum_cgpa": job.get("minimum_cgpa"),
            "required_skills": job.get("required_skills", ""),
            "description": job.get("description", ""),
        }
    reply = _generate_assistant_reply(message, student_context, application_context)
    now = datetime.now(timezone.utc)

    conversation_id = payload.conversation_id
    if conversation_id and ObjectId.is_valid(conversation_id):
        existing = assistant_conversations_collection.find_one({
            "_id": ObjectId(conversation_id), "user_id": user_id
        })
    else:
        existing = None

    if existing:
        assistant_conversations_collection.update_one(
            {"_id": existing["_id"]},
            {"$push": {"messages": {"$each": [
                {"role": "user", "content": message, "created_at": now},
                {"role": "assistant", "content": reply, "created_at": now},
            ], "$slice": -60}}, "$set": {"updated_at": now}},
        )
        conversation_id = str(existing["_id"])
    else:
        result = assistant_conversations_collection.insert_one({
            "user_id": user_id,
            "messages": [
                {"role": "user", "content": message, "created_at": now},
                {"role": "assistant", "content": reply, "created_at": now},
            ],
            "created_at": now,
            "updated_at": now,
        })
        conversation_id = str(result.inserted_id)

    return {"reply": reply, "conversation_id": conversation_id}


@router.get("/assistant/history")
def assistant_history(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["student"])
    conversation = assistant_conversations_collection.find_one(
        {"user_id": ObjectId(current_user["user_id"])},
        sort=[("updated_at", -1)],
    )
    if not conversation:
        return {"conversation_id": None, "messages": []}
    messages = []
    for item in conversation.get("messages", [])[-30:]:
        messages.append({
            "role": item.get("role"),
            "content": item.get("content"),
            "created_at": item.get("created_at").isoformat()
            if isinstance(item.get("created_at"), datetime) else None,
        })
    return {"conversation_id": str(conversation["_id"]), "messages": messages}
