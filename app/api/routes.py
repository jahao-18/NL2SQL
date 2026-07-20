"""HTTP 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.core.business_domains import (
    auth_payload,
    change_password,
    filter_schema_info,
    login,
    public_role_options,
    role_settings,
    row_scope_context,
    require_admin,
    switch_role,
    token_for,
    user_from_token,
)
from app.core.config import settings
from app.core.data_sources import get_engine, get_source, load_sources
from app.core.examples import delete_example, list_examples, upsert_example
from app.core.feedback import add_feedback, delete_feedback, list_feedback
from app.core.governance import create_feedback_review, create_publish_review, delete_review_items_for_feedback, load_settings
from app.core.judge import stashed_status
from app.core.organization_access import (
    create_position_assignment,
    end_position_assignment,
    transfer_position_assignment,
    update_position_assignment,
    list_organization_units,
    list_class_groups,
    list_position_slots,
    position_assignment_impact,
    list_review_queues,
    list_review_tasks,
    list_staff,
)
from app.core.identity_registration import (
    list_applications,
    batch_review_applications,
    my_application,
    register_account,
    review_application,
)
from app.core.lifecycle import (
    batch_graduate_students,
    lifecycle_impact,
    list_student_lifecycle,
    my_lifecycle_detail,
    my_lifecycle_impact,
    person_lifecycle_detail,
    security_restore_account,
    security_suspend_account,
    confirm_staff_lifecycle,
    request_staff_lifecycle,
    student_lifecycle_action,
)
from app.core.schema import load_schema
from app.core.schema_profile import (
    delete_profile_version,
    list_profile_versions,
    load_profile_dict,
    publish_profile,
    quality_report,
    rollback_profile,
    save_profile_dict,
    update_profile_version,
)
from app.core.teaching_dashboard import teaching_dashboard
from app.core.workbench import build_workbench
from app.core.course_space import add_resource, announcement_receipts, course_space, delete_announcement, get_resource_file, notifications, publish_announcement, publish_announcement_draft, read_notification
from app.models.schemas import (
    AskRequest,
    AskResponse,
    AccountSecurityActionRequest,
    ChangePasswordRequest,
    ConfidenceDetail,
    ExampleListResponse,
    ExampleRequest,
    ExampleResponse,
    FeedbackListResponse,
    FeedbackRequest,
    FeedbackResponse,
    JudgeRequest,
    JudgeResponse,
    LoginRequest,
    RoleSwitchRequest,
    RegisterRequest,
    IdentityReviewRequest,
    IdentityBatchReviewRequest,
    PositionAssignmentCreateRequest,
    PositionAssignmentEndRequest,
    PositionAssignmentUpdateRequest,
    PositionAssignmentTransferRequest,
    ProfileResponse,
    ProfilePublishRequest,
    ProfileRollbackRequest,
    ProfileUpdateRequest,
    ProfileVersionUpdateRequest,
    ProfileVersionsResponse,
    QualityResponse,
    SchemaResponse,
    StudentBatchGraduationRequest,
    StudentLifecycleActionRequest,
    StaffLifecycleRequest,
    StaffTransferRequest,
    AnnouncementRequest,
    CourseResourceRequest,
    SourceInfo,
    SourcesResponse,
)
from app.service import ask as ask_service

router = APIRouter(prefix="/api")


def _auth(x_demo_token: str | None = Header(None)):
    return user_from_token(x_demo_token)


@router.get("/health")
def health() -> dict:
    database_ok = False
    database_error = ""
    try:
        source = get_source("teaching")
        with get_engine(source).connect() as conn:
            conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception as exc:
        database_error = str(exc)
    api_key_configured = bool(settings.dashscope_api_key)
    return {
        "status": "ok" if database_ok and api_key_configured else "degraded",
        "database": {"ok": database_ok, "source": "teaching", "error": database_error},
        "dashscope": {"configured": api_key_configured},
        "prewarm_enabled": settings.prewarm_enabled,
    }


@router.get("/auth/options")
def auth_options() -> dict:
    return {
        "demo_mode": settings.demo_mode,
        "users": public_role_options() if settings.demo_mode else [],
    }


@router.post("/auth/login")
def auth_login(req: LoginRequest) -> dict:
    try:
        ctx = login(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    payload = auth_payload(ctx, token_for(ctx.username, ctx.role_binding_id))
    payload["role_selection_required"] = len(ctx.available_roles) > 1
    return payload


@router.post("/auth/switch-role")
def auth_switch_role(req: RoleSwitchRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    switched_ctx, token = switch_role(user_from_token(ctx), req.role_binding_id)
    payload = auth_payload(switched_ctx, token)
    payload["role_selection_required"] = False
    return payload


@router.post("/auth/register")
def auth_register(req: RegisterRequest) -> dict:
    try:
        return register_account(
            password=req.password,
            display_name=req.display_name,
            identity_type=req.identity_type,
            identifier=req.identifier,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/auth/session")
def auth_session(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return auth_payload(user_from_token(ctx, allow_pending=True))


@router.get("/auth/application")
def auth_application(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return my_application(user_from_token(ctx, allow_pending=True))


@router.get("/auth/applications")
def auth_applications(status: str = Query("pending"), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = user_from_token(ctx)
    try:
        return list_applications(auth, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/applications/batch-review")
def auth_batch_review_applications(
    req: IdentityBatchReviewRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    auth = user_from_token(ctx)
    try:
        return batch_review_applications(
            auth, req.application_ids, req.decision, req.note
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/applications/{application_id}/review")
def auth_review_application(
    application_id: int,
    req: IdentityReviewRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    auth = user_from_token(ctx)
    try:
        return review_application(auth, application_id, req.decision, req.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/organization/units")
def organization_units(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return list_organization_units(user_from_token(ctx))


@router.get("/organization/staff")
def organization_staff(
    college_id: int | None = Query(None),
    query: str = Query("", max_length=80),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    return list_staff(user_from_token(ctx), college_id, query)


@router.get("/organization/class-groups")
def organization_class_groups(
    college_id: int | None = Query(None),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    return list_class_groups(user_from_token(ctx), college_id)


@router.get("/organization/position-slots")
def organization_position_slots(
    organization_unit_id: int | None = Query(None),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    return list_position_slots(user_from_token(ctx), organization_unit_id)


@router.post("/organization/position-assignments")
def organization_create_position_assignment(
    req: PositionAssignmentCreateRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return create_position_assignment(
            user_from_token(ctx),
            position_slot_id=req.position_slot_id,
            user_id=req.user_id,
            assignment_type=req.assignment_type,
            scope_ids=req.scope_ids,
            valid_from=req.valid_from,
            valid_until=req.valid_until,
            reason=req.reason,
            reauth_password=req.reauth_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/organization/position-assignments/{assignment_id}/end")
def organization_end_position_assignment(
    assignment_id: int,
    req: PositionAssignmentEndRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return end_position_assignment(
            user_from_token(ctx), assignment_id, req.reason, reauth_password=req.reauth_password
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/organization/position-assignments/{assignment_id}/impact")
def organization_position_assignment_impact(
    assignment_id: int,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return position_assignment_impact(user_from_token(ctx), assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/organization/position-assignments/{assignment_id}")
def organization_update_position_assignment(
    assignment_id: int,
    req: PositionAssignmentUpdateRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    auth = user_from_token(ctx)
    try:
        return update_position_assignment(
            auth,
            assignment_id,
            scope_ids=req.scope_ids,
            valid_until=req.valid_until,
            reason=req.reason,
            reauth_password=req.reauth_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/organization/position-assignments/{assignment_id}/transfer")
def organization_transfer_position_assignment(
    assignment_id: int,
    req: PositionAssignmentTransferRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return transfer_position_assignment(
            user_from_token(ctx),
            assignment_id,
            successor_user_id=req.successor_user_id,
            assignment_type=req.assignment_type,
            scope_ids=req.scope_ids,
            valid_from=req.valid_from,
            valid_until=req.valid_until,
            reason=req.reason,
            reauth_password=req.reauth_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/organization/review-queues")
def organization_review_queues(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return list_review_queues(user_from_token(ctx))


@router.get("/organization/review-queues/{queue_id}/tasks")
def organization_review_tasks(
    queue_id: int,
    status: str = Query("pending"),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    return list_review_tasks(user_from_token(ctx), queue_id, status)


@router.get("/lifecycle/me")
def lifecycle_me(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return my_lifecycle_detail(user_from_token(ctx))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/lifecycle/me/impact")
def lifecycle_my_impact(
    event_type: str = Query(..., min_length=3, max_length=60),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return my_lifecycle_impact(user_from_token(ctx), event_type)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/lifecycle/people/{person_identity_id}")
def lifecycle_person(
    person_identity_id: int,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return person_lifecycle_detail(user_from_token(ctx), person_identity_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/lifecycle/people/{person_identity_id}/impact")
def lifecycle_person_impact(
    person_identity_id: int,
    event_type: str = Query(..., min_length=3, max_length=60),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return lifecycle_impact(user_from_token(ctx), person_identity_id, event_type)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/people/{person_identity_id}/security-suspend")
def lifecycle_security_suspend(
    person_identity_id: int,
    req: AccountSecurityActionRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return security_suspend_account(user_from_token(ctx), person_identity_id, req.reason, req.reauth_password)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/people/{person_identity_id}/security-restore")
def lifecycle_security_restore(
    person_identity_id: int,
    req: AccountSecurityActionRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return security_restore_account(user_from_token(ctx), person_identity_id, req.reason, req.reauth_password)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/lifecycle/students")
def lifecycle_students(
    status: str = Query("active", min_length=3, max_length=20),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return list_student_lifecycle(user_from_token(ctx), status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/students/batch-graduation")
def lifecycle_batch_graduation(
    req: StudentBatchGraduationRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return batch_graduate_students(user_from_token(ctx), req.person_identity_ids, req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/students/{person_identity_id}/{event_type}")
def lifecycle_student_action(
    person_identity_id: int,
    event_type: str,
    req: StudentLifecycleActionRequest,
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    try:
        return student_lifecycle_action(user_from_token(ctx), person_identity_id, event_type, req.reason)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/staff/{person_identity_id}/events/{event_type}/request")
def lifecycle_staff_request(person_identity_id: int, event_type: str, req: StaffLifecycleRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return request_staff_lifecycle(user_from_token(ctx), person_identity_id, event_type, req.reason, req.reauth_password)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/staff/{person_identity_id}/transfer/request")
def lifecycle_staff_transfer_request(person_identity_id: int, req: StaffTransferRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return request_staff_lifecycle(user_from_token(ctx), person_identity_id, "staff_transfer", req.reason, req.reauth_password, req.destination_college_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lifecycle/staff/events/{event_id}/confirm")
def lifecycle_staff_confirm(event_id: int, req: StaffLifecycleRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return confirm_staff_lifecycle(user_from_token(ctx), event_id, req.reauth_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/auth/me")
def auth_me(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return {"item": auth_payload(user_from_token(ctx))["user"]}


@router.post("/auth/password")
def update_password(req: ChangePasswordRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = user_from_token(ctx)
    try:
        updated = change_password(auth.username, req.old_password, req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return auth_payload(updated)


@router.get("/business-domains")
def business_domains(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    auth = require_admin(ctx)
    return {**role_settings(), "current_user": auth_payload(auth)["user"]}


@router.get("/teaching/dashboard")
def get_teaching_dashboard(
    term: str | None = Query(None),
    college: str | None = Query(None),
    major: str | None = Query(None),
    course_type: str | None = Query(None),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    # The legacy school-wide analytics endpoint is retained only for the
    # platform administrator. Business roles use the scoped workbench below.
    auth = require_admin(ctx)
    try:
        data = teaching_dashboard(
            "teaching",
            allowed_tables=auth.allowed_tables,
            row_scope=auth.row_scope,
            filters={
                "term": term,
                "college": college,
                "major": major,
                "course_type": course_type,
            },
        )
        data["permission"] = {
            "role": auth.role,
            "role_label": auth.role_label,
            "domains": list(auth.domains),
            "allowed_tables": sorted(auth.allowed_tables),
        }
        return data
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/workbench")
def get_workbench(ctx=Header(None, alias="X-Demo-Token")) -> dict:
    """Return a role-specific home page with all row scopes applied server-side."""
    return build_workbench(user_from_token(ctx))

@router.get("/notifications")
def notification_list(unread_only: bool = Query(False), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return notifications(user_from_token(ctx), unread_only)

@router.post("/notifications/{notification_id}/read")
def notification_read(notification_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try: return read_notification(user_from_token(ctx), notification_id)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc))

@router.get("/teaching/classes/{teaching_class_id}/space")
def teaching_course_space(teaching_class_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return course_space(user_from_token(ctx), teaching_class_id)

@router.post("/teaching/classes/{teaching_class_id}/announcements")
def teaching_publish_announcement(teaching_class_id: int, req: AnnouncementRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return publish_announcement(user_from_token(ctx), teaching_class_id, req.title, req.body)

@router.post("/teaching/announcements/{announcement_id}/publish")
def teaching_publish_announcement_draft(announcement_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return publish_announcement_draft(user_from_token(ctx), announcement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/teaching/announcements/{announcement_id}/receipts")
def teaching_announcement_receipts(announcement_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    return announcement_receipts(user_from_token(ctx), announcement_id)

@router.delete("/teaching/announcements/{announcement_id}")
def teaching_delete_announcement(announcement_id: int, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return delete_announcement(user_from_token(ctx), announcement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/teaching/classes/{teaching_class_id}/resources")
def teaching_add_resource(teaching_class_id: int, req: CourseResourceRequest, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    try:
        return add_resource(user_from_token(ctx), teaching_class_id, req.title, req.description, req.file_name, req.file_content_base64, req.content_type, req.resource_url, req.visible_from, req.visible_until)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/teaching/resources/{resource_id}/file")
def teaching_resource_file(resource_id: int, ctx=Header(None, alias="X-Demo-Token")):
    try:
        path, file_name, content_type = get_resource_file(user_from_token(ctx), resource_id)
        return FileResponse(path, filename=file_name, media_type=content_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sources", response_model=SourcesResponse)
def list_sources(ctx=Header(None, alias="X-Demo-Token")) -> SourcesResponse:
    auth = user_from_token(ctx)
    if "ask" not in auth.features:
        raise HTTPException(status_code=403, detail="当前工作身份没有智能问数权限")
    sources = load_sources()
    visible_sources = list(sources.values()) if auth.is_admin else [source for source in sources.values() if source.name == "teaching"]
    items = [
        SourceInfo(name=s.name, label=f"{s.label} · {auth.role_label}", dialect=s.dialect)
        for s in visible_sources
    ]
    if not items:
        raise HTTPException(status_code=503, detail="教学数据源未配置")
    return SourcesResponse(sources=items, default=items[0].name)


@router.get("/schema", response_model=SchemaResponse)
def get_schema(source: str | None = Query(None), ctx=Header(None, alias="X-Demo-Token")) -> SchemaResponse:
    auth = require_admin(ctx)
    try:
        info = filter_schema_info(load_schema(source), auth.allowed_tables, auth.denied_columns)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # 只返回纯表结构(CREATE TABLE);取值发现/业务词表/派生指标是喂 LLM 的,不展示给用户
    return SchemaResponse(tables=info.tables, ddl=info.pure_ddl, columns=info.columns)


@router.get("/profile", response_model=ProfileResponse)
def get_profile(source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> ProfileResponse:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ProfileResponse(source=source, profile=load_profile_dict(source))


@router.put("/profile", response_model=ProfileResponse)
def update_profile(req: ProfileUpdateRequest, source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> ProfileResponse:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    saved = save_profile_dict(source, req.profile)
    return ProfileResponse(source=source, profile=saved)


@router.get("/profile/versions", response_model=ProfileVersionsResponse)
def get_profile_versions(source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> ProfileVersionsResponse:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ProfileVersionsResponse(items=list_profile_versions(source))


@router.post("/profile/publish")
def publish_profile_endpoint(req: ProfilePublishRequest | None = None, source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    req = req or ProfilePublishRequest()
    settings = load_settings()
    if settings.get("require_publish_note") and not req.description.strip():
        raise HTTPException(status_code=400, detail="发布说明不能为空")
    if settings.get("review_required_for_publish"):
        item = create_publish_review(source, label=req.label, description=req.description)
        return {"published": False, "review_required": True, "item": item}
    return publish_profile(source, label=req.label, description=req.description)


@router.post("/profile/rollback", response_model=ProfileResponse)
def rollback_profile_endpoint(req: ProfileRollbackRequest, source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> ProfileResponse:
    require_admin(ctx)
    try:
        get_source(source)
        profile = rollback_profile(source, req.version_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"version not found: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ProfileResponse(source=source, profile=profile)


@router.put("/profile/versions/{version_id}")
def update_profile_version_endpoint(
    version_id: str,
    req: ProfileVersionUpdateRequest,
    source: str = Query(...),
    ctx=Header(None, alias="X-Demo-Token"),
) -> dict:
    require_admin(ctx)
    try:
        get_source(source)
        item = update_profile_version(source, version_id, label=req.label, description=req.description)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"version not found: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.delete("/profile/versions/{version_id}")
def delete_profile_version_endpoint(version_id: str, source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    require_admin(ctx)
    try:
        get_source(source)
        delete_profile_version(source, version_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"version not found: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"deleted": True}


@router.get("/quality", response_model=QualityResponse)
def get_quality(source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> QualityResponse:
    require_admin(ctx)
    try:
        info = load_schema(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return QualityResponse(report=quality_report(source, info.tables))


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, ctx=Header(None, alias="X-Demo-Token")) -> AskResponse:
    auth = user_from_token(ctx)
    if "ask" not in auth.features:
        raise HTTPException(status_code=403, detail="当前工作身份没有智能问数权限")
    requested_source = req.source
    current_source = req.current_source
    if not auth.is_admin:
        if requested_source not in {None, "teaching"}:
            raise HTTPException(status_code=403, detail="当前工作身份只能查询教学业务数据源")
        requested_source = "teaching"
        current_source = "teaching"
    try:
        # 校验 source 存在(若给了)
        if requested_source is not None:
            get_source(requested_source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    scoped_glossary = list(req.user_glossary)
    scope_hint = row_scope_context(auth)
    if scope_hint:
        scoped_glossary.append(scope_hint)
    scoped_glossary.append("“本学期”默认指 teaching_class.year = 2025 AND teaching_class.semester = 'spring'。")
    result = ask_service(req.question, history=req.history, source=requested_source,
                         current_source=current_source, user_glossary=scoped_glossary,
                         few_shots=req.few_shots, allowed_tables=auth.allowed_tables,
                         denied_columns=auth.denied_columns,
                         denied_terms=auth.denied_terms,
                         role_label=auth.role_label, row_scope=auth.row_scope)
    return AskResponse(**result)


@router.post("/judge", response_model=JudgeResponse)
def judge(req: JudgeRequest, ctx=Header(None, alias="X-Demo-Token")) -> JudgeResponse:
    """异步准确率评估:凭 /api/ask 返回的 judge_id 取件并跑裁判。best-effort,失败/过期返回空。"""
    user_from_token(ctx)
    status, jr = stashed_status(req.judge_id)
    if jr is None:
        return JudgeResponse(confidence=None, confidence_detail=None, status=status)
    return JudgeResponse(
        confidence=jr.final,
        confidence_detail=ConfidenceDetail(
            retrieval=jr.retrieval, correctness=jr.correctness, reason=jr.reason
        ),
        status="done",
    )


@router.post("/feedback", response_model=FeedbackResponse)
def create_feedback(req: FeedbackRequest, ctx=Header(None, alias="X-Demo-Token")) -> FeedbackResponse:
    user_from_token(ctx)
    item = add_feedback(req.model_dump())
    create_feedback_review(item)
    return FeedbackResponse(item=item)


@router.get("/feedback", response_model=FeedbackListResponse)
def get_feedback(source: str | None = Query(None), limit: int = Query(100, ge=1, le=500), ctx=Header(None, alias="X-Demo-Token")) -> FeedbackListResponse:
    require_admin(ctx)
    return FeedbackListResponse(items=list_feedback(source, limit))


@router.delete("/feedback/{item_id}")
def remove_feedback(item_id: str, ctx=Header(None, alias="X-Demo-Token")) -> dict:
    require_admin(ctx)
    try:
        item = delete_feedback(item_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="feedback not found")
    deleted_reviews = delete_review_items_for_feedback(item_id)
    return {"deleted": True, "item": item, "deleted_reviews": deleted_reviews}


@router.get("/examples", response_model=ExampleListResponse)
def get_examples(source: str = Query(...), limit: int = Query(200, ge=1, le=500), ctx=Header(None, alias="X-Demo-Token")) -> ExampleListResponse:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ExampleListResponse(items=list_examples(source, limit))


@router.post("/examples", response_model=ExampleResponse)
def save_example(req: ExampleRequest, source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> ExampleResponse:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ExampleResponse(item=upsert_example(source, req.model_dump()))


@router.delete("/examples/{item_id}")
def remove_example(item_id: str, source: str = Query(...), ctx=Header(None, alias="X-Demo-Token")) -> dict:
    require_admin(ctx)
    try:
        get_source(source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    delete_example(source, item_id)
    return {"deleted": True}
