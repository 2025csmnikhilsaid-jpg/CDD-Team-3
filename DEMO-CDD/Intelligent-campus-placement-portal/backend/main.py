import hashlib
import os
import secrets
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from pymongo.errors import DuplicateKeyError

from database import (
    applications_collection,
    check_database_connection,
    jobs_collection,
    notifications_collection,
    users_collection,
)
from email_service import send_application_status_email


SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "campusconnect_change_this_to_a_long_random_secret_key",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
security = HTTPBearer()

MARKSHEET_DIR = Path(os.getenv("MARKSHEET_DIR", "/app/uploads/marksheets"))
MARKSHEET_DIR.mkdir(parents=True, exist_ok=True)
MAX_MARKSHEET_SIZE = 10 * 1024 * 1024
ALLOWED_MARKSHEET_TYPES = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}


def save_marksheet_file(upload: UploadFile) -> dict:
    original_name = Path(upload.filename or "marksheet").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_MARKSHEET_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Upload a PDF, JPG, JPEG or PNG marksheet.",
        )

    if upload.content_type not in ALLOWED_MARKSHEET_TYPES[extension]:
        raise HTTPException(
            status_code=400,
            detail="The marksheet file type is not valid.",
        )

    content = upload.file.read(MAX_MARKSHEET_SIZE + 1)

    if not content:
        raise HTTPException(status_code=400, detail="The marksheet file is empty.")

    if len(content) > MAX_MARKSHEET_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Marksheet must be 10 MB or smaller.",
        )

    valid_signature = (
        (extension == ".pdf" and content.startswith(b"%PDF-"))
        or (
            extension in {".jpg", ".jpeg"}
            and content.startswith(b"\xff\xd8\xff")
        )
        or (
            extension == ".png"
            and content.startswith(b"\x89PNG\r\n\x1a\n")
        )
    )

    if not valid_signature:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file does not match its file extension.",
        )

    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = MARKSHEET_DIR / stored_name
    destination.write_bytes(content)

    return {
        "stored_name": stored_name,
        "original_name": original_name,
        "content_type": upload.content_type,
        "size": len(content),
    }


app = FastAPI(
    title="Intelligent Campus Placement Portal",
    description="A centralized platform for campus recruitment and placement management.",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
        )

    if not user_id or not ObjectId.is_valid(str(user_id)):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token.",
        )

    user = users_collection.find_one({"_id": ObjectId(user_id)})

    if not user:
        raise HTTPException(status_code=401, detail="User account not found.")

    return {
        "user_id": str(user["_id"]),
        "name": user.get("full_name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "department": user.get("department"),
        "graduation_year": user.get("graduation_year"),
    }


def require_role(user: dict, allowed_roles: list[str]) -> dict:
    if user.get("role") not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this resource.",
        )
    return user


def verify_owner(current_user: dict, requested_id: str) -> None:
    if current_user["user_id"] != str(requested_id):
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this account.",
        )


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100000
    ).hex()
    return f"{salt}${hashed}"


def verify_password(password: str, stored_password: str) -> bool:
    try:
        salt, stored_hash = stored_password.split("$", 1)
        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 100000
        ).hex()
        return secrets.compare_digest(calculated_hash, stored_hash)
    except (ValueError, AttributeError):
        return False


def find_by_id(collection, record_id):
    if not ObjectId.is_valid(str(record_id)):
        return None
    return collection.find_one({"_id": ObjectId(str(record_id))})


def get_recruiter(recruiter_id: str):
    recruiter = find_by_id(users_collection, recruiter_id)
    if not recruiter or recruiter.get("role") != "recruiter":
        raise HTTPException(status_code=404, detail="Recruiter not found.")
    return recruiter


def get_job_recruiter_id(job: dict) -> Optional[str]:
    recruiter_id = job.get("recruiter_id")
    return str(recruiter_id) if recruiter_id else None


def get_application_date(application: dict) -> str:
    applied_at = application.get("applied_at")
    if isinstance(applied_at, datetime):
        return applied_at.isoformat()
    if applied_at:
        return str(applied_at)
    return application["_id"].generation_time.isoformat()


def get_job_id_query(job_id: str) -> dict:
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID.")
    return {"_id": ObjectId(job_id)}


def get_application_id_query(application_id: str) -> dict:
    if not ObjectId.is_valid(application_id):
        raise HTTPException(status_code=400, detail="Invalid application ID.")
    return {"_id": ObjectId(application_id)}


def create_application_notification(
    user_id: str, title: str, message: str
) -> None:
    if not ObjectId.is_valid(str(user_id)):
        return

    notifications_collection.insert_one(
        {
            "user_id": ObjectId(str(user_id)),
            "title": title,
            "message": message,
            "category": "application",
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
        }
    )


def serialize_job(job: dict) -> dict:
    recruiter_id = get_job_recruiter_id(job)
    created_at = job.get("created_at")

    return {
        "id": str(job["_id"]),
        "company": job.get("company_name", job.get("company", "")),
        "title": job.get("job_title", job.get("title", "")),
        "company_name": job.get("company_name", job.get("company", "")),
        "job_title": job.get("job_title", job.get("title", "")),
        "description": job.get("description", ""),
        "minimum_cgpa": job.get("minimum_cgpa", 0.0),
        "department": job.get("eligible_department", job.get("department")),
        "eligible_department": job.get(
            "eligible_department", job.get("department")
        ),
        "skills": job.get("required_skills", job.get("skills", "")),
        "required_skills": job.get("required_skills", job.get("skills", "")),
        "salary": job.get("salary_package", job.get("salary", "")),
        "salary_package": job.get("salary_package", job.get("salary", "")),
        "graduation_year": job.get(
            "eligible_graduation_year", job.get("graduation_year")
        ),
        "eligible_graduation_year": job.get(
            "eligible_graduation_year", job.get("graduation_year")
        ),
        "location": job.get("job_location", job.get("location", "")),
        "job_location": job.get("job_location", job.get("location", "")),
        "application_deadline": job.get("application_deadline"),
        "recruiter_id": recruiter_id,
        "created_at": (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else created_at
        ),
    }


def serialize_application(application: dict) -> dict:
    student_id = application.get("student_id")
    job_id = application.get("job_id")
    student = find_by_id(users_collection, student_id)
    job = find_by_id(jobs_collection, job_id)

    student_name = (
        student.get("full_name", "")
        if student
        else application.get("student_name", "")
    )
    student_email = (
        student.get("email", "")
        if student
        else application.get("student_email", "")
    )
    company = (
        job.get("company_name", job.get("company", ""))
        if job
        else application.get("company", "")
    )
    job_title = (
        job.get("job_title", job.get("title", ""))
        if job
        else application.get("job_title", application.get("title", ""))
    )
    applied_at = get_application_date(application)

    return {
        "id": str(application["_id"]),
        "application_id": str(application["_id"]),
        "student_id": str(student_id),
        "student_name": student_name,
        "student_email": student_email,
        "department": (
            student.get("department")
            if student
            else application.get("department")
        ),
        "graduation_year": (
            student.get("graduation_year")
            if student
            else application.get("graduation_year")
        ),
        "job_id": str(job_id),
        "company": company,
        "title": job_title,
        "job_title": job_title,
        "cgpa": application.get("cgpa"),
        "status": application.get("status", "Applied"),
        "applied_at": applied_at,
        "date_applied": applied_at,
    }


def validate_job_values(values: dict) -> None:
    if "minimum_cgpa" in values:
        cgpa = values["minimum_cgpa"]
        if cgpa is not None and not 0 <= cgpa <= 10:
            raise HTTPException(
                status_code=400,
                detail="Minimum CGPA must be between 0 and 10.",
            )

    if "eligible_graduation_year" in values:
        year = values["eligible_graduation_year"]
        if year is not None and not 2020 <= year <= 2040:
            raise HTTPException(
                status_code=400,
                detail="Invalid eligible graduation year.",
            )

    deadline_value = values.get("application_deadline")
    if deadline_value:
        try:
            deadline = date.fromisoformat(deadline_value)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid application deadline. Use YYYY-MM-DD.",
            )

        if deadline < datetime.now(timezone.utc).date():
            raise HTTPException(
                status_code=400,
                detail="Application deadline cannot be in the past.",
            )


def get_recruiter_jobs(recruiter_id: str) -> list:
    return list(jobs_collection.find({"recruiter_id": ObjectId(recruiter_id)}))


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str
    department: Optional[str] = None
    graduation_year: Optional[int] = None


class JobCreate(BaseModel):
    company_name: str
    job_title: str
    description: str
    minimum_cgpa: float = 0.0
    eligible_department: Optional[str] = None
    required_skills: Optional[str] = None
    salary_package: Optional[str] = None
    eligible_graduation_year: Optional[int] = None
    job_location: Optional[str] = None
    application_deadline: Optional[str] = None
    recruiter_id: str


class JobUpdate(BaseModel):
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    description: Optional[str] = None
    minimum_cgpa: Optional[float] = None
    eligible_department: Optional[str] = None
    required_skills: Optional[str] = None
    salary_package: Optional[str] = None
    eligible_graduation_year: Optional[int] = None
    job_location: Optional[str] = None
    application_deadline: Optional[str] = None


class ApplicationCreate(BaseModel):
    student_id: str
    job_id: str
    cgpa: Optional[float] = None


class AcademicVerificationUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class AcademicRejectionRequest(BaseModel):
    reason: str


class ApplicationStatusUpdate(BaseModel):
    status: str


@app.get("/")
def home():
    return {
        "message": "Welcome to Intelligent Campus Placement Portal",
        "status": "Running",
        "version": "2.2.0",
    }


@app.get("/health")
def health_check():
    if not check_database_connection():
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )
    return {"status": "healthy", "database": "connected"}


@app.post("/register")
def register_user(user: UserCreate):
    if user.role not in ["student", "recruiter"]:
        raise HTTPException(
            status_code=400,
            detail="Public registration is available only for students and recruiters.",
        )

    if not user.full_name.strip() or len(user.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Enter a name and a password containing at least 8 characters.",
        )

    if user.role == "student":
        raise HTTPException(
            status_code=400,
            detail="Student registration must include CGPA and marksheet. Use the student registration form.",
        )

    email = str(user.email).strip().lower()

    if users_collection.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered.")

    new_user = {
        "full_name": user.full_name.strip(),
        "email": email,
        "password": hash_password(user.password),
        "role": user.role,
        "department": user.department,
        "graduation_year": user.graduation_year,
    }

    try:
        result = users_collection.insert_one(new_user)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered.")

    return {
        "message": "Registration successful",
        "user_id": str(result.inserted_id),
        "name": user.full_name.strip(),
        "email": email,
        "role": user.role,
    }


@app.post("/register/student")
def register_student_with_marksheet(
    full_name: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    department: str = Form(...),
    graduation_year: int = Form(...),
    cgpa: float = Form(...),
    marksheet: UploadFile = File(...),
):
    if len(full_name.strip()) < 3 or len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Enter a full name and a password with at least 8 characters.",
        )

    if not department.strip() or not 2020 <= graduation_year <= 2040:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid department and graduation year.",
        )

    if not math.isfinite(cgpa) or not 0 <= cgpa <= 10:
        raise HTTPException(
            status_code=400,
            detail="CGPA must be between 0 and 10.",
        )

    normalized_email = str(email).strip().lower()

    # NIE email restriction applies to students only.
    if not normalized_email.endswith("@nie.ac.in"):
        raise HTTPException(
            status_code=400,
            detail="Please use your NIE college email ID ending with @nie.ac.in.",
        )

    if users_collection.find_one({"email": normalized_email}):
        raise HTTPException(status_code=400, detail="Email already registered.")

    saved = save_marksheet_file(marksheet)
    now = datetime.now(timezone.utc)

    student_data = {
        "full_name": full_name.strip(),
        "email": normalized_email,
        "password": hash_password(password),
        "role": "student",
        "department": department.strip(),
        "graduation_year": graduation_year,
        "declared_cgpa": round(float(cgpa), 2),
        "verified_cgpa": None,
        "academic_verification_status": "Pending",
        "academic_verification_reason": None,
        "marksheet_file": saved["stored_name"],
        "marksheet_original_name": saved["original_name"],
        "marksheet_content_type": saved["content_type"],
        "marksheet_size": saved["size"],
        "marksheet_uploaded_at": now,
        "created_at": now,
    }

    try:
        result = users_collection.insert_one(student_data)
    except DuplicateKeyError:
        (MARKSHEET_DIR / saved["stored_name"]).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Email already registered.")

    return {
        "message": "Student registration successful. Your marksheet is awaiting admin verification.",
        "user_id": str(result.inserted_id),
        "name": full_name.strip(),
        "email": normalized_email,
        "role": "student",
        "academic_verification_status": "Pending",
    }


@app.post("/login")
def login_user(email: EmailStr, password: str):
    normalized_email = str(email).strip().lower()
    user = users_collection.find_one({"email": normalized_email})

    if not user or not verify_password(password, user.get("password")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    access_token = create_access_token({"sub": str(user["_id"])})

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(user["_id"]),
        "name": user.get("full_name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "department": user.get("department"),
        "graduation_year": user.get("graduation_year"),
    }


@app.get("/auth/me")
def get_logged_in_user(current_user: dict = Depends(get_current_user)):
    return {"message": "Authentication successful", "user": current_user}


@app.get("/students/me")
def get_student_profile(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["student"])
    student = users_collection.find_one(
        {"_id": ObjectId(current_user["user_id"])}
    ) or {}

    return {
        "id": current_user["user_id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user["role"],
        "department": current_user["department"],
        "graduation_year": current_user["graduation_year"],
        "declared_cgpa": student.get("declared_cgpa"),
        "verified_cgpa": student.get("verified_cgpa"),
        "academic_verification_status": student.get(
            "academic_verification_status", "Not Submitted"
        ),
        "academic_verification_reason": student.get(
            "academic_verification_reason"
        ),
    }


@app.get("/users")
def get_users(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["admin"])

    return [
        {
            "id": str(user["_id"]),
            "name": user.get("full_name", ""),
            "email": user.get("email", ""),
            "role": user.get("role", ""),
            "department": user.get("department"),
            "graduation_year": user.get("graduation_year"),
        }
        for user in users_collection.find()
    ]


@app.get("/students/me/academic-verification")
def student_academic_verification(
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["student"])
    student = users_collection.find_one(
        {"_id": ObjectId(current_user["user_id"])}
    ) or {}

    status = student.get("academic_verification_status", "Not Submitted")
    reason = student.get("academic_verification_reason")

    # Return both naming conventions for compatibility with existing frontend code.
    return {
        "declared_cgpa": student.get("declared_cgpa"),
        "verified_cgpa": student.get("verified_cgpa"),
        "status": status,
        "academic_verification_status": status,
        "reason": reason,
        "rejection_reason": reason,
        "academic_verification_reason": reason,
        "marksheet_uploaded": bool(student.get("marksheet_file")),
    }


@app.post("/students/me/academic-documents")
def submit_student_academic_documents(
    cgpa: float = Form(...),
    marksheet: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["student"])

    if not math.isfinite(cgpa) or not 0 <= cgpa <= 10:
        raise HTTPException(
            status_code=400,
            detail="CGPA must be between 0 and 10.",
        )

    student_id = ObjectId(current_user["user_id"])
    student = users_collection.find_one({"_id": student_id})

    if not student:
        raise HTTPException(status_code=404, detail="Student account not found.")

    saved = save_marksheet_file(marksheet)
    old_file = student.get("marksheet_file")

    users_collection.update_one(
        {"_id": student_id},
        {
            "$set": {
                "declared_cgpa": round(float(cgpa), 2),
                "verified_cgpa": None,
                "academic_verification_status": "Pending",
                "academic_verification_reason": None,
                "marksheet_file": saved["stored_name"],
                "marksheet_original_name": saved["original_name"],
                "marksheet_content_type": saved["content_type"],
                "marksheet_size": saved["size"],
                "marksheet_uploaded_at": datetime.now(timezone.utc),
            }
        },
    )

    if old_file and old_file != saved["stored_name"]:
        (MARKSHEET_DIR / Path(old_file).name).unlink(missing_ok=True)

    return {
        "message": "Academic documents submitted. Verification is pending.",
        "status": "Pending",
        "academic_verification_status": "Pending",
    }


@app.get("/admin/academic-verifications")
def list_academic_verifications(
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["admin"])
    records = users_collection.find({"role": "student"}).sort(
        "marksheet_uploaded_at", -1
    )

    results = []

    for student in records:
        student_id = str(student["_id"])
        name = student.get("full_name", "")
        status = student.get("academic_verification_status", "Not Submitted")
        reason = student.get("academic_verification_reason")

        results.append(
            {
                "student_id": student_id,
                "user_id": student_id,
                "id": student_id,
                "name": name,
                "full_name": name,
                "email": student.get("email", ""),
                "department": student.get("department", ""),
                "graduation_year": student.get("graduation_year"),
                "declared_cgpa": student.get("declared_cgpa"),
                "verified_cgpa": student.get("verified_cgpa"),
                "status": status,
                "academic_verification_status": status,
                "reason": reason,
                "rejection_reason": reason,
                "marksheet_uploaded": bool(student.get("marksheet_file")),
                "marksheet_original_name": student.get(
                    "marksheet_original_name"
                ),
            }
        )

    return results


@app.get("/admin/academic-verifications/{student_id}/marksheet")
def view_student_marksheet(
    student_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["admin"])

    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=400, detail="Invalid student ID.")

    student = users_collection.find_one(
        {"_id": ObjectId(student_id), "role": "student"}
    )

    if not student or not student.get("marksheet_file"):
        raise HTTPException(status_code=404, detail="Marksheet not found.")

    path = MARKSHEET_DIR / Path(student["marksheet_file"]).name

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Marksheet file is missing from storage.",
        )

    return FileResponse(
        path,
        media_type=student.get(
            "marksheet_content_type", "application/octet-stream"
        ),
        filename=student.get("marksheet_original_name", path.name),
        content_disposition_type="inline",
    )


def set_academic_verification(
    student_id: str,
    status: str,
    reason: Optional[str],
    current_user: dict,
) -> dict:
    """Shared validation and update logic for PUT and admin POST actions."""
    require_role(current_user, ["admin"])

    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=400, detail="Invalid student ID.")

    if status not in {"Verified", "Rejected"}:
        raise HTTPException(
            status_code=400,
            detail="Status must be Verified or Rejected.",
        )

    student_object_id = ObjectId(student_id)
    student = users_collection.find_one(
        {"_id": student_object_id, "role": "student"}
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    if not student.get("marksheet_file") or student.get("declared_cgpa") is None:
        raise HTTPException(
            status_code=400,
            detail="Student has not submitted a CGPA and marksheet.",
        )

    if status == "Rejected" and not (reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Provide a reason when rejecting a marksheet.",
        )

    fields = {
        "academic_verification_status": status,
        "academic_verification_reason": (
            (reason or "").strip() if status == "Rejected" else None
        ),
        "academic_verified_at": datetime.now(timezone.utc),
        "academic_verified_by": ObjectId(current_user["user_id"]),
        "verified_cgpa": (
            float(student["declared_cgpa"]) if status == "Verified" else None
        ),
    }

    users_collection.update_one(
        {"_id": student_object_id},
        {"$set": fields},
    )

    return {
        "message": f"Academic record {status.lower()} successfully.",
        "student_id": student_id,
        "status": status,
        "academic_verification_status": status,
        "verified_cgpa": fields["verified_cgpa"],
        "reason": fields["academic_verification_reason"],
        "rejection_reason": fields["academic_verification_reason"],
    }


@app.put("/admin/academic-verifications/{student_id}")
def update_academic_verification(
    student_id: str,
    update: AcademicVerificationUpdate,
    current_user: dict = Depends(get_current_user),
):
    return set_academic_verification(
        student_id=student_id,
        status=update.status,
        reason=update.reason,
        current_user=current_user,
    )


@app.post("/admin/academic-verifications/{student_id}/approve")
def approve_student_academic_verification(
    student_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Approve a student's uploaded marksheet using the Admin account."""
    return set_academic_verification(
        student_id=student_id,
        status="Verified",
        reason=None,
        current_user=current_user,
    )


@app.post("/admin/academic-verifications/{student_id}/reject")
def reject_student_academic_verification(
    student_id: str,
    rejection: AcademicRejectionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Reject a student's uploaded marksheet with a mandatory reason."""
    return set_academic_verification(
        student_id=student_id,
        status="Rejected",
        reason=rejection.reason,
        current_user=current_user,
    )


@app.post("/jobs")
def create_job(
    job: JobCreate,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter"])
    verify_owner(current_user, job.recruiter_id)
    get_recruiter(current_user["user_id"])

    validate_job_values(
        {
            "minimum_cgpa": job.minimum_cgpa,
            "eligible_graduation_year": job.eligible_graduation_year,
            "application_deadline": job.application_deadline,
        }
    )

    if not job.company_name.strip() or not job.job_title.strip():
        raise HTTPException(
            status_code=400,
            detail="Company name and job title are required.",
        )

    if not job.description.strip():
        raise HTTPException(status_code=400, detail="Job description is required.")

    job_data = job.model_dump()
    job_data["company_name"] = job.company_name.strip()
    job_data["job_title"] = job.job_title.strip()
    job_data["description"] = job.description.strip()
    job_data["recruiter_id"] = ObjectId(current_user["user_id"])
    job_data["created_at"] = datetime.now(timezone.utc)

    result = jobs_collection.insert_one(job_data)

    return {
        "message": "Job posted successfully",
        "job_id": str(result.inserted_id),
    }


@app.get("/jobs")
def get_all_jobs():
    jobs = jobs_collection.find().sort("created_at", -1)
    return [serialize_job(job) for job in jobs]


@app.put("/jobs/{job_id}")
def update_job(
    job_id: str,
    job_update: JobUpdate,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter", "admin"])
    existing_job = jobs_collection.find_one(get_job_id_query(job_id))

    if not existing_job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if current_user["role"] == "recruiter":
        if get_job_recruiter_id(existing_job) != current_user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail="You can update only your own job postings.",
            )

    update_data = job_update.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No job details were provided for update.",
        )

    for field in ["company_name", "job_title", "description"]:
        if field in update_data:
            value = update_data[field]
            if value is None or not str(value).strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"{field} cannot be empty.",
                )
            update_data[field] = str(value).strip()

    validate_job_values(update_data)

    jobs_collection.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": update_data},
    )

    updated_job = jobs_collection.find_one({"_id": ObjectId(job_id)})

    return {
        "message": "Job updated successfully",
        "job": serialize_job(updated_job),
    }


@app.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter", "admin"])
    existing_job = jobs_collection.find_one(get_job_id_query(job_id))

    if not existing_job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if current_user["role"] == "recruiter":
        if get_job_recruiter_id(existing_job) != current_user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail="You can delete only your own job postings.",
            )

    if applications_collection.find_one({"job_id": ObjectId(job_id)}):
        raise HTTPException(
            status_code=400,
            detail="This job cannot be deleted because applications already exist.",
        )

    jobs_collection.delete_one({"_id": ObjectId(job_id)})

    return {"message": "Job deleted successfully", "job_id": job_id}


@app.get("/recruiters/{recruiter_id}/dashboard")
def recruiter_dashboard(
    recruiter_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter"])
    verify_owner(current_user, recruiter_id)

    recruiter_jobs = get_recruiter_jobs(recruiter_id)
    job_ids = [job["_id"] for job in recruiter_jobs]
    applications = list(
        applications_collection.find({"job_id": {"$in": job_ids}})
    )

    return {
        "total_jobs": len(recruiter_jobs),
        "total_applications": len(applications),
        "shortlisted": sum(
            1 for item in applications if item.get("status") == "Shortlisted"
        ),
        "selected": sum(
            1 for item in applications if item.get("status") == "Selected"
        ),
    }


@app.get("/recruiters/{recruiter_id}/jobs")
def get_recruiter_job_list(
    recruiter_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter"])
    verify_owner(current_user, recruiter_id)

    jobs = list(
        jobs_collection.find({"recruiter_id": ObjectId(recruiter_id)}).sort(
            "created_at", -1
        )
    )

    results = []

    for job in jobs:
        item = serialize_job(job)
        item["applicant_count"] = applications_collection.count_documents(
            {"job_id": job["_id"]}
        )
        results.append(item)

    return results


@app.get("/recruiters/{recruiter_id}/applicants")
def get_recruiter_applicants(
    recruiter_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter"])
    verify_owner(current_user, recruiter_id)

    recruiter_jobs = get_recruiter_jobs(recruiter_id)
    job_ids = [job["_id"] for job in recruiter_jobs]
    applications = applications_collection.find(
        {"job_id": {"$in": job_ids}}
    ).sort("applied_at", -1)

    return [serialize_application(item) for item in applications]


@app.post("/applications")
def apply_for_job(
    application: ApplicationCreate,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["student"])
    verify_owner(current_user, application.student_id)

    if not ObjectId.is_valid(application.student_id):
        raise HTTPException(status_code=400, detail="Invalid student ID.")

    if not ObjectId.is_valid(application.job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID.")

    student_id = ObjectId(current_user["user_id"])
    job_id = ObjectId(application.job_id)
    student = users_collection.find_one({"_id": student_id})
    job = jobs_collection.find_one({"_id": job_id})

    if not student:
        raise HTTPException(status_code=404, detail="Student account not found.")

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if (
        student.get("academic_verification_status") != "Verified"
        or student.get("verified_cgpa") is None
    ):
        status = student.get(
            "academic_verification_status", "Not Submitted"
        )

        if status == "Rejected":
            detail = (
                "Your marksheet was rejected. Upload a corrected marksheet before applying."
            )
        elif status == "Pending":
            detail = (
                "Your marksheet is awaiting admin verification. You can apply after it is approved."
            )
        else:
            detail = (
                "Submit your CGPA and marksheet, then wait for admin verification before applying."
            )

        raise HTTPException(status_code=403, detail=detail)

    verified_cgpa = float(student["verified_cgpa"])

    deadline_value = job.get("application_deadline")

    if deadline_value:
        try:
            deadline = date.fromisoformat(deadline_value)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="The job has an invalid application deadline.",
            )

        if deadline < datetime.now(timezone.utc).date():
            raise HTTPException(
                status_code=400,
                detail="The application deadline has passed.",
            )

    if verified_cgpa < float(job.get("minimum_cgpa", 0) or 0):
        raise HTTPException(
            status_code=400,
            detail="Your CGPA does not meet the minimum requirement.",
        )

    eligible_department = job.get(
        "eligible_department", job.get("department")
    )

    if eligible_department:
        required_department = str(eligible_department).strip().casefold()
        student_department = str(
            student.get("department") or ""
        ).strip().casefold()

        if (
            required_department not in {"all departments", "all"}
            and required_department != student_department
        ):
            raise HTTPException(
                status_code=400,
                detail="Your department is not eligible for this job.",
            )

    eligible_year = job.get(
        "eligible_graduation_year", job.get("graduation_year")
    )

    if (
        eligible_year is not None
        and student.get("graduation_year") != eligible_year
    ):
        raise HTTPException(
            status_code=400,
            detail="Your graduation year is not eligible for this job.",
        )

    existing_application = applications_collection.find_one(
        {"student_id": student_id, "job_id": job_id}
    )

    if existing_application:
        raise HTTPException(
            status_code=400,
            detail="You have already applied for this job.",
        )

    new_application = {
        "student_id": student_id,
        "job_id": job_id,
        "cgpa": verified_cgpa,
        "status": "Applied",
        "applied_at": datetime.now(timezone.utc),
    }

    try:
        result = applications_collection.insert_one(new_application)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400,
            detail="You have already applied for this job.",
        )

    recruiter_id = get_job_recruiter_id(job)

    if recruiter_id:
        create_application_notification(
            recruiter_id,
            "New Job Application",
            f"{student.get('full_name', 'A student')} applied for "
            f"{job.get('job_title', job.get('title', 'your job'))}.",
        )

    return {
        "message": "Application submitted successfully",
        "application_id": str(result.inserted_id),
        "status": "Applied",
    }


@app.get("/students/{student_id}/applications")
def get_student_applications(
    student_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["student"])
    verify_owner(current_user, student_id)

    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=400, detail="Invalid student ID.")

    applications = applications_collection.find(
        {"student_id": ObjectId(student_id)}
    ).sort("applied_at", -1)

    return [serialize_application(item) for item in applications]


@app.get("/applications")
def get_all_applications(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["admin"])
    applications = applications_collection.find().sort("applied_at", -1)
    return [serialize_application(item) for item in applications]


@app.put("/applications/{application_id}/status")
def update_application_status(
    application_id: str,
    status: Optional[str] = None,
    status_update: Optional[ApplicationStatusUpdate] = Body(default=None),
    current_user: dict = Depends(get_current_user),
):
    require_role(current_user, ["recruiter"])

    requested_status = status or (
        status_update.status if status_update is not None else None
    )
    allowed_statuses = [
        "Applied",
        "Shortlisted",
        "Selected",
        "Rejected",
    ]

    if requested_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Choose Applied, Shortlisted, Selected or Rejected.",
        )

    application = applications_collection.find_one(
        get_application_id_query(application_id)
    )

    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")

    job = find_by_id(jobs_collection, application.get("job_id"))

    if not job:
        raise HTTPException(
            status_code=404,
            detail="The job associated with this application was not found.",
        )

    if get_job_recruiter_id(job) != current_user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail="You can update applications only for your own job postings.",
        )

    student_record = find_by_id(
        users_collection, application.get("student_id")
    )

    if requested_status in {"Shortlisted", "Selected"}:
        if (
            not student_record
            or student_record.get("academic_verification_status") != "Verified"
        ):
            raise HTTPException(
                status_code=403,
                detail="This student's academic record is not verified. Shortlisting and selection are blocked.",
            )

        if float(application.get("cgpa", 0) or 0) < float(
            job.get("minimum_cgpa", 0) or 0
        ):
            raise HTTPException(
                status_code=403,
                detail="The student's verified CGPA does not meet this job's minimum requirement.",
            )

    applications_collection.update_one(
        {"_id": ObjectId(application_id)},
        {
            "$set": {
                "status": requested_status,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    student = find_by_id(users_collection, application.get("student_id"))
    student_id = str(application.get("student_id"))
    job_title = job.get(
        "job_title", job.get("title", "your application")
    )
    company_name = job.get(
        "company_name", job.get("company", "the company")
    )

    create_application_notification(
        student_id,
        "Application Status Updated",
        f"Your application for {job_title} at {company_name} is now {requested_status}.",
    )

    if student and student.get("email"):
        try:
            send_application_status_email(
                student.get("full_name", "Student"),
                student["email"],
                job_title,
                company_name,
                requested_status,
            )
        except Exception as email_error:
            print(
                "Application status email could not be sent:",
                email_error,
            )

    return {
        "message": "Application status updated successfully",
        "application_id": application_id,
        "status": requested_status,
    }


@app.get("/admin/dashboard")
def admin_dashboard(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["admin"])

    total_users = users_collection.count_documents({})
    total_students = users_collection.count_documents({"role": "student"})
    total_recruiters = users_collection.count_documents({"role": "recruiter"})
    total_jobs = jobs_collection.count_documents({})
    total_applications = applications_collection.count_documents({})
    shortlisted = applications_collection.count_documents(
        {"status": "Shortlisted"}
    )
    selected = applications_collection.count_documents(
        {"status": "Selected"}
    )
    pending = applications_collection.count_documents(
        {"status": {"$in": ["Applied", "Pending"]}}
    )

    return {
        "total_users": total_users,
        "total_students": total_students,
        "total_recruiters": total_recruiters,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "shortlisted": shortlisted,
        "selected": selected,
        "pending": pending,
    }


@app.get("/analytics/placement-history")
def placement_history(current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["student", "admin"])

    selected_applications = applications_collection.find(
        {"status": "Selected"}
    )
    placed_students_by_year = {}

    for application in selected_applications:
        selected_at = (
            application.get("updated_at")
            or application.get("applied_at")
        )

        if not isinstance(selected_at, datetime):
            continue

        year = str(selected_at.year)
        placed_students_by_year.setdefault(year, set()).add(
            str(application.get("student_id"))
        )

    return [
        {
            "year": year,
            "placed": len(placed_students_by_year[year]),
        }
        for year in sorted(placed_students_by_year)
    ]


from features import router as features_router

app.include_router(features_router)
