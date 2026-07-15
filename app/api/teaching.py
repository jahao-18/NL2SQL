"""Teaching workflow APIs with service-layer authorization."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.assignment_workflow import (
    create_assignment,
    get_assignment,
    get_submission,
    get_submission_file,
    grade_submission,
    list_assignment_roster,
    list_class_assignments,
    list_my_classes,
    list_my_assignments,
    publish_assignment,
    publish_assignment_grades,
    return_submission,
    submit_assignment,
    update_assignment,
)
from app.core.authorization import (
    connect,
    list_class_submissions,
    require_course_member,
    require_submission_access,
    require_support_case_access,
    require_teacher_of_class,
)
from app.core.business_domains import user_from_token
from app.core.course_analytics import (
    analytics_contexts,
    ask_course,
    course_summary,
    query_history,
    save_query_feedback,
)
from app.core.support_workflow import (
    create_support_request,
    get_support_case,
    list_support_cases,
    list_support_requests,
    refresh_support_cases,
    transition_support_case,
    update_support_request,
)


router = APIRouter(prefix="/api/teaching", tags=["teaching"])


class AssignmentCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    instructions: str = Field("", max_length=4000)
    due_time: str = Field(..., min_length=1, max_length=80)
    max_score: float = Field(100, gt=0, le=1000)
    assignment_type: str = Field("homework", max_length=40)
    weight: float = Field(0.1, ge=0, le=1)
    allow_late: bool = True
    status: str = Field("published", pattern="^(draft|published)$")


class SubmissionCreateRequest(BaseModel):
    content: str = Field("", max_length=10000)
    file_name: str | None = Field(None, max_length=255)
    file_content_base64: str | None = Field(None, max_length=7_000_000)
    retain_existing_file: bool = True


class ReturnRequest(BaseModel):
    feedback: str = Field(..., min_length=1, max_length=2000)


class GradeRequest(BaseModel):
    score: float = Field(..., ge=0, le=1000)
    feedback: str = Field("", max_length=2000)


class SupportTransitionRequest(BaseModel):
    target_status: str = Field(..., pattern="^(contacted|tracking|improved|closed)$")
    note: str = Field(..., min_length=1, max_length=2000)
    contact_method: str | None = Field(None, max_length=40)
    student_feedback: str | None = Field(None, max_length=2000)
    follow_up_at: str | None = Field(None, max_length=80)
    visible_to_student: bool = False


class SupportRequestCreate(BaseModel):
    request_type: str = Field("appointment", pattern="^(appointment|consultation)$")
    message: str = Field(..., min_length=1, max_length=2000)
    preferred_time: str | None = Field(None, max_length=80)


class SupportRequestUpdate(BaseModel):
    status: str = Field(..., pattern="^(accepted|completed|declined)$")
    response: str = Field(..., min_length=1, max_length=2000)


class AnalyticsAskRequest(BaseModel):
    teaching_class_id: int = Field(..., gt=0)
    question: str = Field(..., min_length=1, max_length=500)


class AnalyticsFeedbackRequest(BaseModel):
    feedback: str = Field(..., pattern="^(helpful|not_helpful)$")


def _auth(token: str | None):
    return user_from_token(token)


def _handle(fn):
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analytics/contexts")
def course_analytics_contexts(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": analytics_contexts(_auth(ctx))}


@router.get("/analytics/summary")
def course_analytics_summary(teaching_class_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return course_summary(_auth(ctx), teaching_class_id)


@router.post("/analytics/ask")
def course_analytics_ask(req: AnalyticsAskRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return _handle(lambda: ask_course(_auth(ctx), req.teaching_class_id, req.question))


@router.get("/analytics/history")
def course_analytics_history(teaching_class_id: int, limit: int = 10, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": query_history(_auth(ctx), teaching_class_id, limit)}


@router.patch("/analytics/history/{log_id}/feedback")
def course_analytics_feedback(log_id: int, req: AnalyticsFeedbackRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": _handle(lambda: save_query_feedback(_auth(ctx), log_id, req.feedback))}


@router.get("/classes/{teaching_class_id}")
def class_detail(teaching_class_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    scope = require_course_member(auth, teaching_class_id)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT tc.id, c.name AS course_name, t.name AS teacher_name,
                   tc.year, tc.semester, tc.classroom
            FROM teaching_class tc
            JOIN course c ON c.id = tc.course_id
            JOIN teacher t ON t.id = tc.teacher_id
            WHERE tc.id = ?
            """,
            (teaching_class_id,),
        ).fetchone()
    return {"item": dict(row), "scope": scope.data}


@router.get("/classes")
def my_classes(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": list_my_classes(_auth(ctx))}


@router.get("/classes/{teaching_class_id}/assignments")
def class_assignments(teaching_class_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": list_class_assignments(_auth(ctx), teaching_class_id)}


@router.get("/classes/{teaching_class_id}/submissions")
def class_submissions(teaching_class_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    require_teacher_of_class(auth, teaching_class_id)
    return {"items": list_class_submissions(auth, teaching_class_id)}


@router.post("/classes/{teaching_class_id}/assignments")
def create_class_assignment(teaching_class_id: int, req: AssignmentCreateRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {"item": _handle(lambda: create_assignment(auth, teaching_class_id, req.model_dump()))}


@router.get("/assignments/my")
def my_assignments(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {"items": list_my_assignments(auth)}


@router.get("/assignments/{assignment_id}")
def assignment_detail(assignment_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {"item": get_assignment(auth, assignment_id)}


@router.put("/assignments/{assignment_id}")
def update_assignment_endpoint(assignment_id: int, req: AssignmentCreateRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": _handle(lambda: update_assignment(_auth(ctx), assignment_id, req.model_dump()))}


@router.post("/assignments/{assignment_id}/submit")
def submit_assignment_endpoint(assignment_id: int, req: SubmissionCreateRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {
        "item": _handle(
            lambda: submit_assignment(
                auth,
                assignment_id,
                req.content,
                req.file_name,
                req.file_content_base64,
                req.retain_existing_file,
            )
        )
    }


@router.post("/assignments/{assignment_id}/publish-grades")
def publish_grades_endpoint(assignment_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return _handle(lambda: publish_assignment_grades(auth, assignment_id))


@router.post("/assignments/{assignment_id}/publish")
def publish_assignment_endpoint(assignment_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": _handle(lambda: publish_assignment(_auth(ctx), assignment_id))}


@router.get("/assignments/{assignment_id}/roster")
def assignment_roster(assignment_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": list_assignment_roster(_auth(ctx), assignment_id)}


@router.get("/submissions/{submission_id}")
def submission_detail(submission_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {"item": get_submission(auth, submission_id)}


@router.get("/submissions/{submission_id}/versions/{version_no}/file")
def submission_file(submission_id: int, version_no: int, ctx=Header(None, alias="X-Demo-Token")):
    path, file_name = _handle(lambda: get_submission_file(_auth(ctx), submission_id, version_no))
    return FileResponse(path, filename=file_name)


@router.post("/submissions/{submission_id}/return")
def return_submission_endpoint(submission_id: int, req: ReturnRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {"item": _handle(lambda: return_submission(auth, submission_id, req.feedback))}


@router.post("/submissions/{submission_id}/grade")
def grade_submission_endpoint(submission_id: int, req: GradeRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = _auth(ctx)
    return {"item": _handle(lambda: grade_submission(auth, submission_id, req.score, req.feedback))}


@router.get("/support/cases")
def support_cases(status: str | None = None, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": list_support_cases(_auth(ctx), status)}


@router.post("/support/cases/refresh")
def refresh_cases(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return refresh_support_cases(_auth(ctx))


@router.get("/support/cases/{case_id}")
def support_case_detail(case_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": get_support_case(_auth(ctx), case_id)}


@router.post("/support/cases/{case_id}/transition")
def transition_case(case_id: int, req: SupportTransitionRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {
        "item": _handle(
            lambda: transition_support_case(
                _auth(ctx),
                case_id,
                req.target_status,
                req.model_dump(exclude={"target_status"}),
            )
        )
    }


@router.get("/support/requests")
def support_requests(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"items": list_support_requests(_auth(ctx))}


@router.post("/support/requests")
def create_request(req: SupportRequestCreate, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": _handle(lambda: create_support_request(_auth(ctx), req.model_dump()))}


@router.patch("/support/requests/{request_id}")
def update_request(request_id: int, req: SupportRequestUpdate, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": _handle(lambda: update_support_request(_auth(ctx), request_id, req.status, req.response))}
