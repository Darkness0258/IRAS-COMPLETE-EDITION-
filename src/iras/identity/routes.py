"""Face ID endpoints. Every one needs the normal IRAS access token.

  GET    /v1/identity/status
  GET    /v1/identity/people
  POST   /v1/identity/people                 { name }
  DELETE /v1/identity/people/{person_id}     forget a person and all their faceprints
  POST   /v1/identity/face/enroll            { person_id | name, image }
  POST   /v1/identity/face/verify            { image, frames?: [image, ...], require_liveness? }

`image` is a JPEG or PNG as base64 or a data URL. Pictures are looked at and
thrown away. Only the faceprint (512 numbers) of an enrolled person is stored.
"""
from __future__ import annotations

import base64
from typing import Any, Callable

from fastapi import Header, HTTPException

from . import store as ids
from .face import FaceError, FaceUnavailable, engine


def _bytes(image: Any) -> bytes:
    text = str(image or "")
    if "," in text[:80]:
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=False)
    except Exception as exc:
        raise FaceError("I could not read that picture.") from exc


def register_identity_routes(app, authorize: Callable[[str | None], Any], get_db: Callable[[], Any]) -> None:
    holder: dict[str, Any] = {}

    def store() -> ids.IdentityStore:
        if "store" not in holder:
            holder["store"] = ids.IdentityStore(get_db())
        return holder["store"]

    def failure(exc: Exception):
        if isinstance(exc, FaceUnavailable):
            raise HTTPException(status_code=503, detail=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/v1/identity/status")
    def identity_status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        eng = engine()
        problem = eng.tools_missing()
        return {
            "available": not problem,
            "reason": problem,
            "models_ready": bool(not problem and eng.models_ready()),
            "threshold": ids.THRESHOLD,
            "people": len(store().people()),
        }

    @app.get("/v1/identity/people")
    def identity_people(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return {"people": store().people()}

    @app.post("/v1/identity/people")
    def identity_add_person(body: dict, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            return {"person": store().add_person(body.get("name"))}
        except ValueError as exc:
            failure(exc)

    @app.delete("/v1/identity/people/{person_id}")
    def identity_delete_person(person_id: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        store().delete_person(person_id)
        return {"deleted": person_id}

    @app.post("/v1/identity/face/enroll")
    def identity_face_enroll(body: dict, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            person = store().person(str(body.get("person_id") or "")) if body.get("person_id") else None
            if person is None and body.get("name"):
                person = store().find_by_name(body.get("name")) or store().add_person(body.get("name"))
            if person is None:
                raise ValueError("Say who this is first.")
            face, vector = engine().one_face(_bytes(body.get("image")))
            samples = store().add_face(person["person_id"], vector)
            return {"ok": True, "person": {"person_id": person["person_id"], "name": person["name"]}, "samples": samples,
                    "quality": {"score": round(face.score, 2), "width": int(face.width)}}
        except (FaceError, FaceUnavailable, ValueError) as exc:
            failure(exc)

    @app.post("/v1/identity/face/verify")
    def identity_face_verify(body: dict, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            eng = engine()
            faces, vector = eng.analyze(_bytes(body.get("image")))
            if not faces:
                return {"faces": 0, "match": None, "closest": None, "liveness": None, "message": "I cannot see a face."}
            turns: list[float] = []
            for frame in (body.get("frames") or [])[:8]:
                try:
                    found, _ = eng.analyze(_bytes(frame))
                except FaceError:
                    continue
                if found:
                    turns.append(found[0].turn)
            live = ids.check_liveness(turns) if turns else None
            result = ids.decide(vector, store().samples(), store().names())
            message = ""
            if body.get("require_liveness") and not (live and live["passed"]):
                result["match"] = None
                message = "Turn your head slowly left and right, then try again."
            elif result["match"] is None:
                message = "I do not know you yet." if result["closest"] is None else "I am not sure who that is."
            return {"faces": len(faces), "match": result["match"], "closest": result["closest"], "liveness": live, "message": message}
        except (FaceError, FaceUnavailable) as exc:
            failure(exc)
