
/* ============================================================
   CAREERSPHERE - COMPLETE ACADEMIC VERIFICATION SYSTEM
   Version: 2.3.0

   FEATURES:
   1. Student registration with CGPA and marksheet upload
   2. Student email validation (@nie.ac.in)
   3. Student academic verification status
   4. Marksheets resubmission after rejection
   5. Admin academic verification queue
   6. Admin marksheet viewing
   7. Admin approve and reject actions
   8. JWT Bearer authentication

   API: http://127.0.0.1:8002
============================================================ */

(function () {

    "use strict";

    const API = "http://127.0.0.1:8002";

    const MAX_FILE_SIZE = 10 * 1024 * 1024;

    const ALLOWED_FILE_TYPES = [
        "application/pdf",
        "image/jpeg",
        "image/png"
    ];

    /* ========================================================
       COMMON HELPERS
    ======================================================== */

    function getUser() {

        try {

            return JSON.parse(
                sessionStorage.getItem("campusconnectUser") || "null"
            );

        } catch (error) {

            console.error("Unable to read user session:", error);

            return null;
        }
    }

    function getToken() {

        const user = getUser();

        return user?.access_token ||
               user?.token ||
               user?.accessToken ||
               user?.jwt ||
               "";
    }

    function getAuthHeaders(extraHeaders = {}) {

        const token = getToken();

        if (!token) {

            throw new Error(
                "Your login session has expired. Please log in again."
            );
        }

        return {
            ...extraHeaders,
            Authorization: `Bearer ${token}`
        };
    }

    async function api(url, options = {}) {

        const headers = getAuthHeaders(options.headers || {});

        const response = await fetch(API + url, {
            ...options,
            headers
        });

        let result = {};

        try {

            result = await response.json();

        } catch (error) {

            result = {};
        }

        if (!response.ok) {

            throw new Error(
                result.detail ||
                result.message ||
                `Server error: ${response.status}`
            );
        }

        return result;
    }

    function escapeHTML(value) {

        return String(value ?? "").replace(
            /[&<>"']/g,
            character => ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#039;"
            })[character]
        );
    }

    function showMessage(element, message, type = "info") {

        if (!element) return;

        element.className = `alert alert-${type}`;
        element.textContent = message;
        element.classList.remove("d-none");
        element.hidden = false;
    }

    function validateMarksheet(file) {

        if (!file) {

            throw new Error("Please upload your marksheet.");
        }

        if (file.size > MAX_FILE_SIZE) {

            throw new Error(
                "Marksheet must not exceed 10 MB."
            );
        }

        if (!ALLOWED_FILE_TYPES.includes(file.type)) {

            throw new Error(
                "Only PDF, JPG, JPEG and PNG files are allowed."
            );
        }

        return true;
    }

    function getFormValue(form, selectors) {

        for (const selector of selectors) {

            const element = form.querySelector(selector);

            if (element && element.value.trim()) {

                return element.value.trim();
            }
        }

        return "";
    }

    /* ========================================================
       1. STUDENT REGISTRATION FIELDS
    ======================================================== */

    function initializeRegistration() {

        const form = document.getElementById("registerForm");

        if (!form) return;

        const roleElement = document.getElementById("accountRole");

        if (!roleElement) return;

        const studentFieldsId = "academicRegistrationFields";

        function createStudentFields() {

            let container = document.getElementById(studentFieldsId);

            if (!container) {

                container = document.createElement("div");

                container.id = studentFieldsId;

                container.innerHTML = `
                    <div class="mb-3">
                        <label for="academicCgpa" class="form-label">
                            Declared CGPA
                        </label>

                        <input
                            type="number"
                            class="form-control"
                            id="academicCgpa"
                            name="cgpa"
                            min="0"
                            max="10"
                            step="0.01"
                            placeholder="Enter your CGPA"
                        >
                    </div>

                    <div class="mb-3">
                        <label for="marksheetFile" class="form-label">
                            Upload Latest Marksheet
                        </label>

                        <input
                            type="file"
                            class="form-control"
                            id="marksheetFile"
                            name="marksheet"
                            accept=".pdf,.jpg,.jpeg,.png"
                        >

                        <small class="text-muted">
                            Accepted formats: PDF, JPG, JPEG and PNG.
                            Maximum size: 10 MB.
                        </small>
                    </div>
                `;

                const submitButton =
                    form.querySelector(
                        'button[type="submit"], input[type="submit"]'
                    );

                if (submitButton) {

                    submitButton.parentElement.before(container);

                } else {

                    form.appendChild(container);
                }
            }

            return container;
        }

        function updateRegistrationFields() {

            const role = String(
                roleElement.value || ""
            ).toLowerCase();

            if (role === "student") {

                createStudentFields();

            } else {

                const fields =
                    document.getElementById(studentFieldsId);

                if (fields) fields.remove();
            }
        }

        roleElement.addEventListener(
            "change",
            updateRegistrationFields
        );

        updateRegistrationFields();

        /* Capture student registration before other submit handlers. */

        form.addEventListener("submit", async function (event) {

            const role = String(
                roleElement.value || ""
            ).toLowerCase();

            if (role !== "student") return;

            event.preventDefault();
            event.stopImmediatePropagation();

            const messageElement =
                document.getElementById("registerMessage");

            const submitButton =
                form.querySelector(
                    'button[type="submit"], input[type="submit"]'
                );

            const originalButtonText = submitButton
                ? submitButton.innerHTML
                : "";

            try {

                const name = getFormValue(form, [
                    "#fullName",
                    "#registerName",
                    '[name="name"]',
                    '[name="full_name"]'
                ]);

                const email = getFormValue(form, [
                    "#registerEmail",
                    "#email",
                    '[name="email"]'
                ]).toLowerCase();

                const password = getFormValue(form, [
                    "#registerPassword",
                    "#password",
                    '[name="password"]'
                ]);

                const department = getFormValue(form, [
                    "#department",
                    "#studentDepartment",
                    '[name="department"]'
                ]);

                const graduationYear = getFormValue(form, [
                    "#graduationYear",
                    "#graduation_year",
                    '[name="graduation_year"]'
                ]);

                const cgpaInput =
                    document.getElementById("academicCgpa");

                const marksheetInput =
                    document.getElementById("marksheetFile");

                const cgpa = Number(cgpaInput?.value);

                const marksheet = marksheetInput?.files?.[0];

                if (!name || !email || !password) {

                    throw new Error(
                        "Please enter your name, email and password."
                    );
                }

                if (!/^[^\s@]+@nie\.ac\.in$/i.test(email)) {

                    throw new Error(
                        "Student registration requires an @nie.ac.in email address."
                    );
                }

                if (!department || !graduationYear) {

                    throw new Error(
                        "Please enter your department and graduation year."
                    );
                }

                if (
                    !Number.isFinite(cgpa) ||
                    cgpa < 0 ||
                    cgpa > 10
                ) {

                    throw new Error(
                        "Please enter a valid CGPA between 0 and 10."
                    );
                }

                if (
                    !Number.isInteger(Number(graduationYear)) ||
                    Number(graduationYear) < 2020 ||
                    Number(graduationYear) > 2040
                ) {

                    throw new Error(
                        "Please enter a valid graduation year."
                    );
                }

                validateMarksheet(marksheet);

                const formData = new FormData();

                formData.append("name", name);
                formData.append("email", email);
                formData.append("password", password);
                formData.append("department", department);
                formData.append(
                    "graduation_year",
                    String(Number(graduationYear))
                );
                formData.append("cgpa", String(cgpa));
                formData.append("marksheet", marksheet);

                if (submitButton) {

                    submitButton.disabled = true;
                    submitButton.textContent = "Registering...";
                }

                const response = await fetch(
                    `${API}/register/student`,
                    {
                        method: "POST",
                        body: formData
                    }
                );

                let result = {};

                try {
                    result = await response.json();
                } catch (error) {
                    result = {};
                }

                if (!response.ok) {

                    throw new Error(
                        result.detail ||
                        "Student registration failed."
                    );
                }

                showMessage(
                    messageElement,
                    "Student registration successful! Your academic record is awaiting admin verification.",
                    "success"
                );

                form.reset();

                const fields =
                    document.getElementById(studentFieldsId);

                if (fields) {

                    const cgpaField =
                        fields.querySelector("#academicCgpa");

                    const fileField =
                        fields.querySelector("#marksheetFile");

                    if (cgpaField) cgpaField.value = "";
                    if (fileField) fileField.value = "";
                }

            } catch (error) {

                console.error(
                    "Student Registration Error:",
                    error
                );

                showMessage(
                    messageElement,
                    error.message,
                    "danger"
                );

            } finally {

                if (submitButton) {

                    submitButton.disabled = false;
                    submitButton.innerHTML = originalButtonText;
                }
            }

        }, true);
    }

    /* ========================================================
       2. STUDENT ACADEMIC VERIFICATION STATUS
    ======================================================== */

    async function initializeStudentVerification() {

        const user = getUser();

        const page = window.location.pathname.toLowerCase();

        if (!page.endsWith("student-dashboard.html")) return;

        if (
            !user ||
            String(user.role).toLowerCase() !== "student"
        ) return;

        let section = document.getElementById(
            "academicVerificationSection"
        );

        if (!section) {

            section = document.createElement("section");

            section.id = "academicVerificationSection";
            section.className = "card shadow-sm my-4";

            section.innerHTML = `
                <div class="card-body">

                    <h4 class="mb-3">
                        <i class="bi bi-shield-check me-2"></i>
                        Academic Verification
                    </h4>

                    <div id="studentAcademicStatus">
                        Loading academic verification status...
                    </div>

                    <div id="studentAcademicResubmission"></div>

                </div>
            `;

            const mainContainer =
                document.querySelector("main") ||
                document.querySelector(".container");

            if (mainContainer) {

                mainContainer.appendChild(section);
            }
        }

        const statusContainer = document.getElementById(
            "studentAcademicStatus"
        );

        const resubmissionContainer = document.getElementById(
            "studentAcademicResubmission"
        );

        async function loadStudentStatus() {

            statusContainer.innerHTML = `
                <div class="text-center py-3">
                    <div class="spinner-border text-primary"></div>
                    <p class="mt-2">Checking verification status...</p>
                </div>
            `;

            try {

                const result = await api(
                    "/students/me/academic-verification"
                );

                const status =
                    result.academic_verification_status ||
                    result.status ||
                    "Pending";

                const reason =
                    result.rejection_reason ||
                    result.academic_verification_reason ||
                    result.reason ||
                    "";

                let badge = "bg-warning text-dark";

                if (String(status).toLowerCase() === "verified") {
                    badge = "bg-success";
                }

                if (String(status).toLowerCase() === "rejected") {
                    badge = "bg-danger";
                }

                statusContainer.innerHTML = `
                    <p>
                        <strong>Verification Status:</strong>
                        <span class="badge ${badge}">
                            ${escapeHTML(status)}
                        </span>
                    </p>

                    ${
                        reason
                            ? `<div class="alert alert-danger">
                                 <strong>Admin feedback:</strong>
                                 ${escapeHTML(reason)}
                               </div>`
                            : ""
                    }

                    ${
                        String(status).toLowerCase() === "verified"
                            ? `<div class="alert alert-success">
                                 Your academic record has been verified.
                               </div>`
                            : String(status).toLowerCase() === "pending"
                                ? `<div class="alert alert-info">
                                     Your marksheet is awaiting admin review.
                                   </div>`
                                : `<div class="alert alert-warning">
                                     Your academic document requires correction.
                                   </div>`
                    }
                `;

                if (
                    String(status).toLowerCase() === "rejected"
                ) {

                    renderResubmissionForm();

                } else {

                    resubmissionContainer.innerHTML = "";
                }

            } catch (error) {

                console.error(
                    "Student Verification Status Error:",
                    error
                );

                statusContainer.innerHTML = `
                    <div class="alert alert-danger">
                        Unable to load verification status:
                        ${escapeHTML(error.message)}
                    </div>
                `;
            }
        }

        function renderResubmissionForm() {

            resubmissionContainer.innerHTML = `
                <hr>

                <h5>Resubmit Academic Documents</h5>

                <p class="text-muted">
                    Upload a corrected marksheet and enter your updated CGPA.
                </p>

                <form id="academicResubmissionForm">

                    <div class="mb-3">

                        <label class="form-label" for="resubmissionCgpa">
                            Updated CGPA
                        </label>

                        <input
                            type="number"
                            class="form-control"
                            id="resubmissionCgpa"
                            min="0"
                            max="10"
                            step="0.01"
                            required
                        >

                    </div>

                    <div class="mb-3">

                        <label class="form-label" for="resubmissionMarksheet">
                            Corrected Marksheet
                        </label>

                        <input
                            type="file"
                            class="form-control"
                            id="resubmissionMarksheet"
                            accept=".pdf,.jpg,.jpeg,.png"
                            required
                        >

                    </div>

                    <div id="resubmissionMessage"></div>

                    <button
                        type="submit"
                        class="btn btn-primary"
                        id="resubmitAcademicButton"
                    >
                        <i class="bi bi-upload me-1"></i>
                        Resubmit Documents
                    </button>

                </form>
            `;

            const form = document.getElementById(
                "academicResubmissionForm"
            );

            form.addEventListener("submit", async function(event) {

                event.preventDefault();

                const cgpa = Number(
                    document.getElementById(
                        "resubmissionCgpa"
                    ).value
                );

                const file = document.getElementById(
                    "resubmissionMarksheet"
                ).files[0];

                const message = document.getElementById(
                    "resubmissionMessage"
                );

                const button = document.getElementById(
                    "resubmitAcademicButton"
                );

                try {

                    if (
                        !Number.isFinite(cgpa) ||
                        cgpa < 0 ||
                        cgpa > 10
                    ) {

                        throw new Error(
                            "Enter a valid CGPA between 0 and 10."
                        );
                    }

                    validateMarksheet(file);

                    const formData = new FormData();

                    formData.append("cgpa", String(cgpa));
                    formData.append("marksheet", file);

                    button.disabled = true;
                    button.textContent = "Uploading...";

                    const response = await fetch(
                        `${API}/students/me/academic-documents`,
                        {
                            method: "POST",
                            headers: getAuthHeaders(),
                            body: formData
                        }
                    );

                    let result = {};

                    try {
                        result = await response.json();
                    } catch (error) {
                        result = {};
                    }

                    if (!response.ok) {

                        throw new Error(
                            result.detail ||
                            "Unable to resubmit documents."
                        );
                    }

                    showMessage(
                        message,
                        "Documents resubmitted successfully. Your academic record is awaiting admin review.",
                        "success"
                    );

                    await loadStudentStatus();

                } catch (error) {

                    showMessage(
                        message,
                        error.message,
                        "danger"
                    );

                } finally {

                    button.disabled = false;

                    button.innerHTML =
                        '<i class="bi bi-upload me-1"></i> Resubmit Documents';
                }
            });
        }

        await loadStudentStatus();
    }

    /* ========================================================
       3. ADMIN ACADEMIC VERIFICATION MANAGEMENT
    ======================================================== */

    function initializeAdminVerification() {

        const page = window.location.pathname.toLowerCase();

        if (!page.endsWith("admin-dashboard.html")) return;

        const user = getUser();

        const queue = document.getElementById(
            "academicVerificationQueue"
        );

        if (!queue) {

            console.error(
                "academicVerificationQueue element not found."
            );

            return;
        }

        if (
            !user ||
            String(user.role).toLowerCase() !== "admin"
        ) {

            queue.innerHTML = `
                <div class="alert alert-danger">
                    Please log in using your administrator account.
                </div>
            `;

            return;
        }

        function getStudentId(student) {

            return student.student_id ||
                   student.user_id ||
                   student.id ||
                   student._id ||
                   "";
        }

        function getStudentStatus(student) {

            return student.academic_verification_status ||
                   student.status ||
                   "Pending";
        }

        function getStatusBadge(status) {

            const normalized = String(status).toLowerCase();

            if (normalized === "verified") {
                return "bg-success";
            }

            if (normalized === "rejected") {
                return "bg-danger";
            }

            return "bg-warning text-dark";
        }

        function showAdminMessage(message, type = "info") {

            let messageElement = document.getElementById(
                "academicVerificationMessage"
            );

            if (!messageElement) {

                messageElement = document.createElement("div");

                messageElement.id =
                    "academicVerificationMessage";

                queue.before(messageElement);
            }

            showMessage(
                messageElement,
                message,
                type
            );
        }

        function renderQueue(students) {

            if (
                !Array.isArray(students) ||
                students.length === 0
            ) {

                queue.innerHTML = `
                    <div class="alert alert-success">
                        <i class="bi bi-check-circle-fill me-2"></i>
                        No academic verification records found.
                    </div>
                `;

                return;
            }

            queue.innerHTML = students.map(student => {

                const studentId = getStudentId(student);

                const status = getStudentStatus(student);

                const pending =
                    String(status).toLowerCase() === "pending";

                const name = escapeHTML(
                    student.name ||
                    student.full_name ||
                    "Student"
                );

                const email = escapeHTML(student.email);

                const department = escapeHTML(
                    student.department
                );

                const year = escapeHTML(
                    student.graduation_year ||
                    student.year
                );

                const cgpa = escapeHTML(
                    student.declared_cgpa ??
                    student.cgpa ??
                    "Not available"
                );

                const reason = escapeHTML(
                    student.rejection_reason ||
                    student.academic_verification_reason ||
                    student.reason ||
                    ""
                );

                return `
                    <div class="card shadow-sm mb-3">

                        <div class="card-body">

                            <div class="d-flex justify-content-between
                                        align-items-start flex-wrap gap-2">

                                <div>

                                    <h5 class="mb-1">${name}</h5>

                                    <p class="text-muted small mb-0">
                                        ${email}
                                    </p>

                                </div>

                                <span class="badge ${getStatusBadge(status)}">
                                    ${escapeHTML(status)}
                                </span>

                            </div>

                            <hr>

                            <div class="row g-3">

                                <div class="col-md-3">
                                    <strong>Department</strong>
                                    <div>${department}</div>
                                </div>

                                <div class="col-md-3">
                                    <strong>Graduation Year</strong>
                                    <div>${year}</div>
                                </div>

                                <div class="col-md-3">
                                    <strong>Declared CGPA</strong>
                                    <div>${cgpa}</div>
                                </div>

                                <div class="col-md-3">
                                    <strong>Verification Status</strong>
                                    <div>${escapeHTML(status)}</div>
                                </div>

                            </div>

                            ${
                                reason
                                    ? `<div class="alert alert-danger mt-3 mb-0">
                                         <strong>Rejection reason:</strong>
                                         ${reason}
                                       </div>`
                                    : ""
                            }

                            <div class="d-flex gap-2 flex-wrap mt-4">

                                <button
                                    type="button"
                                    class="btn btn-outline-primary view-academic-marksheet"
                                    data-student-id="${escapeHTML(studentId)}"
                                    ${!studentId ? "disabled" : ""}
                                >
                                    <i class="bi bi-file-earmark-pdf me-1"></i>
                                    View Marksheet
                                </button>

                                <button
                                    type="button"
                                    class="btn btn-success approve-academic"
                                    data-student-id="${escapeHTML(studentId)}"
                                    ${!pending || !studentId ? "disabled" : ""}
                                >
                                    <i class="bi bi-check-circle-fill me-1"></i>
                                    Approve
                                </button>

                                <button
                                    type="button"
                                    class="btn btn-danger reject-academic"
                                    data-student-id="${escapeHTML(studentId)}"
                                    ${!pending || !studentId ? "disabled" : ""}
                                >
                                    <i class="bi bi-x-circle-fill me-1"></i>
                                    Reject
                                </button>

                            </div>

                        </div>

                    </div>
                `;

            }).join("");

            attachAdminActions();
        }

        /* ----------------------------------------------------
           VIEW MARKSHEET
        ---------------------------------------------------- */

        function attachAdminActions() {

            queue.querySelectorAll(
                ".view-academic-marksheet"
            ).forEach(button => {

                button.addEventListener("click", async function() {

                    const studentId = this.dataset.studentId;

                    const originalText = this.innerHTML;

                    this.disabled = true;
                    this.textContent = "Opening...";

                    try {

                        const response = await fetch(
                            `${API}/admin/academic-verifications/${encodeURIComponent(studentId)}/marksheet`,
                            {
                                headers: getAuthHeaders()
                            }
                        );

                        if (!response.ok) {

                            let error = {};

                            try {
                                error = await response.json();
                            } catch (e) {}

                            throw new Error(
                                error.detail ||
                                "Unable to open marksheet."
                            );
                        }

                        const blob = await response.blob();

                        const fileURL = URL.createObjectURL(blob);

                        const openedWindow = window.open(
                            fileURL,
                            "_blank"
                        );

                        if (!openedWindow) {

                            const link = document.createElement("a");

                            link.href = fileURL;
                            link.target = "_blank";
                            link.rel = "noopener";
                            link.click();
                        }

                        setTimeout(() => {
                            URL.revokeObjectURL(fileURL);
                        }, 60000);

                    } catch (error) {

                        showAdminMessage(
                            error.message,
                            "danger"
                        );

                    } finally {

                        this.disabled = false;
                        this.innerHTML = originalText;
                    }
                });
            });

            /* ------------------------------------------------
               APPROVE STUDENT
            ------------------------------------------------ */

            queue.querySelectorAll(
                ".approve-academic"
            ).forEach(button => {

                button.addEventListener("click", async function() {

                    const studentId = this.dataset.studentId;

                    const confirmed = confirm(
                        "Are you sure you want to approve this student's academic record?"
                    );

                    if (!confirmed) return;

                    const originalText = this.innerHTML;

                    this.disabled = true;
                    this.textContent = "Approving...";

                    try {

                        await api(
                            `/admin/academic-verifications/${encodeURIComponent(studentId)}/approve`,
                            {
                                method: "POST"
                            }
                        );

                        showAdminMessage(
                            "Student academic record approved successfully.",
                            "success"
                        );

                        await loadAcademicVerifications();

                    } catch (error) {

                        showAdminMessage(
                            error.message,
                            "danger"
                        );

                        this.disabled = false;
                        this.innerHTML = originalText;
                    }
                });
            });

            /* ------------------------------------------------
               REJECT STUDENT
            ------------------------------------------------ */

            queue.querySelectorAll(
                ".reject-academic"
            ).forEach(button => {

                button.addEventListener("click", async function() {

                    const studentId = this.dataset.studentId;

                    const reason = prompt(
                        "Enter the reason for rejecting this student's academic record:"
                    );

                    if (reason === null) return;

                    if (!reason.trim()) {

                        alert(
                            "A rejection reason is required."
                        );

                        return;
                    }

                    const originalText = this.innerHTML;

                    this.disabled = true;
                    this.textContent = "Rejecting...";

                    try {

                        await api(
                            `/admin/academic-verifications/${encodeURIComponent(studentId)}/reject`,
                            {
                                method: "POST",

                                headers: {
                                    "Content-Type": "application/json"
                                },

                                body: JSON.stringify({
                                    reason: reason.trim()
                                })
                            }
                        );

                        showAdminMessage(
                            "Student academic record rejected successfully.",
                            "success"
                        );

                        await loadAcademicVerifications();

                    } catch (error) {

                        showAdminMessage(
                            error.message,
                            "danger"
                        );

                        this.disabled = false;
                        this.innerHTML = originalText;
                    }
                });
            });
        }

        /* ----------------------------------------------------
           LOAD VERIFICATION QUEUE
        ---------------------------------------------------- */

        async function loadAcademicVerifications() {

            queue.innerHTML = `
                <div class="text-center py-4">

                    <div class="spinner-border text-primary"></div>

                    <p class="mt-2">
                        Loading academic verification records...
                    </p>

                </div>
            `;

            try {

                const result = await api(
                    "/admin/academic-verifications"
                );

                const students = Array.isArray(result)
                    ? result
                    : result.students ||
                      result.verifications ||
                      result.records ||
                      [];

                renderQueue(students);

            } catch (error) {

                console.error(
                    "Admin Academic Verification Error:",
                    error
                );

                queue.innerHTML = `
                    <div class="alert alert-danger">

                        <strong>
                            Unable to load academic verification records.
                        </strong>

                        <p class="mt-2 mb-2">
                            ${escapeHTML(error.message)}
                        </p>

                        <button
                            type="button"
                            class="btn btn-outline-danger btn-sm"
                            id="retryAcademicVerification"
                        >
                            <i class="bi bi-arrow-clockwise me-1"></i>
                            Try Again
                        </button>

                    </div>
                `;

                document.getElementById(
                    "retryAcademicVerification"
                )?.addEventListener(
                    "click",
                    loadAcademicVerifications
                );
            }
        }

        /* ----------------------------------------------------
           REFRESH BUTTON
        ---------------------------------------------------- */

        const refreshButton = document.getElementById(
            "refreshAcademicVerificationButton"
        );

        if (refreshButton) {

            refreshButton.addEventListener(
                "click",
                loadAcademicVerifications
            );
        }

        loadAcademicVerifications();
    }

    /* ========================================================
       4. INITIALIZE ALL FEATURES
    ======================================================== */

    function initializeAll() {

        initializeRegistration();

        initializeStudentVerification();

        initializeAdminVerification();
    }

    if (document.readyState === "loading") {

        document.addEventListener(
            "DOMContentLoaded",
            initializeAll
        );

    } else {

        initializeAll();
    }

})();
