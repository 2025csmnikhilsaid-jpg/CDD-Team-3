# CareerSphere upgrade notes

## Enhanced release 2.3.0

- Added a student-only CareerSphere Assistant chat panel.
- Added per-student assistant conversation persistence and history retrieval.
- Added optional Gemini integration through a backend-only environment variable, with a built-in fallback when no key is configured.
- Added eligibility-based job recommendations using department, graduation year and available CGPA fields; no skill-gap analysis is included.
- Added a shared visual refinement stylesheet across student, recruiter and admin dashboards.
- Added frontend Nginx container and a three-service Docker Compose stack.
- Added backend and frontend health checks, explicit CORS origins and safer response headers.
- Expanded GitHub Actions validation for backend tests, frontend syntax and Docker builds.
- Removed a duplicate `script.js` inclusion from the registration page.
- Preserved existing authentication, academic verification, job, application, resume, interview, notification and analytics modules.


## Expo readiness update – 2026-11-19
- Recruiter interview scheduling now displays and accepts readable APP references from an applicant dropdown; MongoDB ObjectIds stay internal.
- Scheduling an interview updates the application to `Interview Scheduled`, and the student timeline now includes that stage.
- Student dashboard application cards display the readable reference.
- Added subtle animated ambient background and restrained CSS 3D card depth, with reduced-motion support.
- Removed local `.env` credentials and uploaded student documents from the distributable archive; `.env.example` remains.

## Dashboard layout refinement
- Dynamic feature panels, including resume upload and interview/notification tools, are positioned immediately below the dashboard welcome banner rather than at the bottom of the page.


## Expo reliability and visual update
- Routed frontend API calls through the frontend Nginx container at `/api`, forwarding to the FastAPI service. This removes hard-coded browser `127.0.0.1` API dependencies and avoids CORS/host-address mismatches when the demo is opened from another device on the same network.
- Disabled stale caching for HTML, CSS and JavaScript so rebuilt frontend assets are picked up reliably.
- Refined the recruiter interview scheduling panel with a responsive two-column form, clearer field styling and stronger visual hierarchy.
- Added a clear backend connection message when the browser cannot reach the API.

## Expo UI continuation — 19 November 2026
- Added `frontend/expo-ui.css`, a cohesive premium visual layer for the public landing page, student dashboard, recruiter dashboard, admin control room, login, and registration pages.
- Added glass-effect navigation, layered gradient hero sections, richer dashboard cards, responsive spacing, modern form focus states, refined typography, hover depth, and reduced-motion support.
- Linked the visual layer after existing page styles so it enhances the current design without replacing application markup, IDs, or JavaScript behavior.


## Expo final polish – 19 Nov 2026
- Added three distinct, locally served dashboard hero photographs for student, recruiter and admin views.
- Improved interview API authentication compatibility by accepting all token property names supported by the main frontend.
- Made API calls explicitly same-origin for localhost and LAN expo access; improved backend connection diagnostics.
- Added a retry control for recruiter applicant loading and upgraded interview cards/form styling.
- Updated dashboard cache-busting versions.
