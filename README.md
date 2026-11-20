# CareerSphere – Intelligent Campus Placement Portal

CareerSphere is a role-based campus recruitment platform for students, recruiters and placement administrators. This release builds on the supplied project rather than replacing its existing authentication, academic verification, job, application, interview and notification workflows.

## Main capabilities

### Student
- Register and sign in to a student account.
- View placement opportunities and apply for jobs.
- Track each application through Applied → Shortlisted → Interview Scheduled → Selected/Rejected, with a visible progress journey and readable `APP-000000` reference.
- Upload a resume and academic documents.
- View academic-verification progress.
- View scheduled interviews.
- See eligibility-based job recommendations using department, graduation year and available CGPA information. This is eligibility matching, not a skill-gap analyser.
- Use the CareerSphere Student Assistant for resume, interview and placement-preparation guidance. Conversation history is stored per student. If `GOOGLE_API_KEY` is not configured, the assistant uses built-in guidance.

### Recruiter
- Create and manage job postings.
- Review applicants and their resumes.
- Update application statuses.
- Schedule interviews by selecting an applicant from a dropdown; the form displays a readable `APP-000000` reference and never asks recruiters to copy/type a MongoDB ObjectId. Interview scheduling updates the student application stage and sends an in-app notification.

### Administrator
- Review users and placement activity.
- Manage platform job and application workflows.
- Review student academic-verification submissions.
- View platform and placement analytics.

## Technology stack

- Frontend: HTML, CSS, JavaScript, Bootstrap
- Backend: Python 3.11, FastAPI
- Database: MongoDB 7 / PyMongo
- Authentication: JWT bearer tokens
- Containerization: Docker and Docker Compose
- CI: GitHub Actions and Pytest

## Project layout

```text
Intelligent-campus-placement-portal/
├── backend/
│   ├── main.py
│   ├── features.py
│   ├── database.py
│   ├── email_service.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── student-dashboard.html
│   ├── recruiter-dashboard.html
│   ├── admin-dashboard.html
│   ├── assistant.js
│   ├── assistant.css
│   └── nginx.conf
├── mongodb-backup/
├── tests/
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Run with Docker Desktop (Windows)

1. Install and start Docker Desktop.
2. Extract this project folder.
3. In PowerShell, open the extracted `Intelligent-campus-placement-portal` directory.
4. Create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Open `.env` and replace `SECRET_KEY` with a long random secret. Keep `.env` private and never commit it. Optionally add a Gemini API key to enable AI-generated assistant responses.
6. Start the complete application:

   ```powershell
   docker compose up -d --build
   ```

7. Open the application at `http://localhost:5501`.
8. Open FastAPI documentation at `http://localhost:8003/docs`.
9. Check container health:

   ```powershell
   docker compose ps
   ```

## Stop and restart

Stop the containers without deleting the database volume:

```powershell
docker compose down
```

Start again:

```powershell
docker compose up -d
```

**Do not run `docker compose down -v`** unless you intentionally want to delete the persistent MongoDB volume. The upgraded Compose project uses its own isolated volume, `carrierspheare_mongodb_data`, and a distinct Compose project name. It does not reuse, stop, or delete the original portal database.

## Local development without Docker

Backend (from `backend`):

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8003
```

Frontend (from `frontend`):

```powershell
python -m http.server 5501
```

MongoDB must be running locally and `MONGO_URL` must point to it. The frontend's browser-side API URL is currently `http://127.0.0.1:8003`.

## Application references and AI assistant

New applications receive a short human-readable reference such as `APP-123456`. Existing applications are assigned a readable reference the first time they are loaded. The MongoDB ObjectId remains an internal database key; recruiters select the displayed application reference from the applicant list.

## Student Assistant configuration

The assistant endpoint is protected by the student's JWT and only permits student accounts. Students can select one of their applications so the assistant can tailor guidance to its current stage. Each conversation is associated with the authenticated student. Configure `GOOGLE_API_KEY` in `.env` to use Gemini-generated responses; without it, the built-in rules-based fallback gives practical placement guidance. A real Gemini API key and internet access are required for generative AI responses. The assistant must not be treated as an authoritative source for live job availability, application decisions or official placement deadlines.

## Tests and CI

Run the tests locally from the project root:

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest -q
```

GitHub Actions checks backend compilation and tests, frontend JavaScript syntax and HTML parsing, Docker Compose configuration, and builds both Docker images.

## Important operational notes

- Never commit `.env`, passwords, API keys or production secrets.
- Configure SMTP variables separately if email notifications are required; email failures should not interrupt application status changes or interview scheduling.
- The included `mongodb-backup` directory is a backup source; mounting it at `/backup` does not automatically restore it. Restore only when deliberately migrating or recovering data.
- Test with a non-production database before importing backups or changing the persistent volume.


## CareerSphere isolated Docker launch (Windows / Docker Desktop)

This upgraded copy is isolated from the original portal: frontend `http://localhost:5501`, backend `http://localhost:8003`, and a dedicated MongoDB volume named `carrierspheare_carrierspheare_mongodb_data`. It does not stop or delete the original project containers or database.

1. Copy `.env.example` to `.env` and set `SECRET_KEY` to a long random value.
2. Open PowerShell in this folder and run `docker compose up --build -d`.
3. Open `http://localhost:5501`. API health: `http://localhost:8003/health`.
4. To stop only this upgraded stack, run `docker compose -p carrierspheare down` from this folder. Do not add `-v` unless you intentionally want to delete this upgraded stack's database volume.

### Placement workflow updates
- Each new student receives a human-readable CareerSphere student code at registration. Each job application receives a readable numeric `APP-...` application reference in addition to its private MongoDB record ID.
- Recruiters choose an applicant/job from their own received-applications dropdown when scheduling interviews; they no longer need to ask candidates to copy/paste database IDs.
- Student application cards show an Applied → Shortlisted → Interview Scheduled → Selected progress journey and the application reference.
- The student assistant includes an application selector and uses the selected application/job/status as context for guidance. Configure `GOOGLE_API_KEY` for Gemini-generated responses; without it, the built-in placement-help fallback remains available.
- CI validates Python, JavaScript, HTML, Compose and Docker builds. CD publishes backend and frontend images to GHCR on pushes to `main`.


### Administrator account setup
Administrator accounts are provisioned by the owner using `python create_admin.py` from the `backend` folder (or `docker compose -p carrierspheare exec backend python create_admin.py` when running in Docker). There is no invitation-code field. Public admin self-registration remains disabled so visitors cannot grant themselves administrator privileges.


### Dashboard visuals

The student and recruiter dashboard hero uses the locally bundled `frontend/campus-students-hero.webp` image. It is served with the frontend, so it does not require an external image URL or a separate download at runtime.


### Administrator account registration

The registration form includes an Administrator role. Admin creation is protected: set `ADMIN_REGISTRATION_CODE` in your local `.env` file before starting Docker. Only people who know this code can create an administrator account. If you leave it blank, admin registration is disabled. Keep this code private and change it after creating the required admin account.
