from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable
import httpx
import json

class HikvisionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: int = 502,
        response: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.response = response

# Hikvision espera formato tipo "2026-02-25T00:00:00" (sin Z)
def fmt(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

#Calidad de imagen
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps

MAX_HIKVISION_FACE_IMAGE_SIZE_BYTES = 200 * 1024  # 200 KB
MAX_HIKVISION_FACE_IMAGE_WIDTH = 600
MAX_HIKVISION_FACE_IMAGE_HEIGHT = 600

def optimize_image_for_hikvision(image_path: str | Path) -> bytes:
    image_path = Path(image_path)

    try:
        image = Image.open(image_path)
    except Exception as e:
        raise HikvisionError(
            f"No se pudo abrir la imagen para optimizarla: {image_path}",
            status=400,
            response=str(e),
        )

    # Corrige orientación de fotos tomadas desde celular
    image = ImageOps.exif_transpose(image)

    # Hikvision suele funcionar mejor con JPEG RGB
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Redimensiona manteniendo proporción
    image.thumbnail(
        (
            MAX_HIKVISION_FACE_IMAGE_WIDTH,
            MAX_HIKVISION_FACE_IMAGE_HEIGHT,
        ),
        Image.Resampling.LANCZOS,
    )

    quality = 85

    while quality >= 40:
        output = BytesIO()

        image.save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=False,
        )

        optimized_bytes = output.getvalue()

        if len(optimized_bytes) <= MAX_HIKVISION_FACE_IMAGE_SIZE_BYTES:
            return optimized_bytes

        quality -= 5

    raise HikvisionError(
        "La imagen sigue siendo demasiado pesada para enviarla al dispositivo Hikvision",
        status=400,
        response=f"Imagen no pudo bajar de {MAX_HIKVISION_FACE_IMAGE_SIZE_BYTES} bytes",
    )

##############################
def build_user_payload(
    *,
    employee_no: str,
    name: str | None = None,
    begin_time: datetime | None = None,
    end_time: datetime | None = None,
    door_no: int | None = None,
    plan_template_no: str | None = None,
    include_user_type: bool = False,
) -> dict:
    if (begin_time is None) != (end_time is None):
        raise ValueError("begin_time and end_time must be provided together")

    if begin_time is not None and end_time is not None and begin_time > end_time:
        raise ValueError("begin_time cannot be greater than end_time")

    user_info = {
        "employeeNo": str(employee_no),
    }

    if name is not None:
        user_info["name"] = name

    if include_user_type:
        user_info["userType"] = "normal"

    if begin_time is not None and end_time is not None:
        user_info["Valid"] = {
            "enable": True,
            "beginTime": fmt(begin_time),
            "endTime": fmt(end_time),
        }

    print(begin_time)
    print(end_time)

    print(fmt(begin_time))
    print(fmt(end_time))


    if door_no is not None:
        user_info["doorRight"] = str(door_no)

    if door_no is not None and plan_template_no is not None:
        user_info["RightPlan"] = [
            {
                "doorNo": int(door_no),
                "planTemplateNo": str(plan_template_no),
            }
        ]

    return {"UserInfo": user_info}

def register_user_on_device(
    *,
    device_ip: str,
    device_username: str,
    device_password: str,
    payload: dict,
    timeout_seconds: float = 10.0,
) -> dict:
    url = f"http://{device_ip}/ISAPI/AccessControl/UserInfo/Record?format=json"

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(
                url,
                json=payload,
                auth=httpx.DigestAuth(device_username, device_password),
                headers={"Content-Type": "application/json"},
            )
    except httpx.RequestError as e:
        raise HikvisionError(
            f"No se pudo conectar al dispositivo ({device_ip}): {e}",
            status=502,
            response=str(e)
        )

    if resp.status_code >= 400:
        raise HikvisionError(
            "Dispositivo rechazó registro",
            status=resp.status_code,
            response=resp.text[:500],
        )

    # Hikvision suele responder JSON; si no, igual devolvemos texto
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}

def update_user_on_device(
        *,
        device_ip: str,
        device_username: str,
        device_password: str,
        payload: dict,
        timeout_seconds: float = 10.0,
)-> dict:
    url = f"http://{device_ip}/ISAPI/AccessControl/UserInfo/Modify?format=json"
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.put(
                url,
                json=payload,
                auth=httpx.DigestAuth(device_username, device_password),
                headers={"Content-Type": "application/json"},
            )
            
    except httpx.RequestError as e:
        raise HikvisionError(
            f"No se pudo conectar al dispositivo ({device_ip}): {e}",
            status=502,
            response=str(e)
        )

    if resp.status_code >= 400:
        raise HikvisionError(
            "Dispositivo rechazó la actualización",
            status=resp.status_code,
            response=resp.text[:500],
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}

def delete_user_from_device(
    *,
    device_ip: str,
    device_username: str,
    device_password: str,
    employee_nos: Iterable[str],
    timeout_seconds: float = 10.0,
) -> dict:
    """
    Borra usuarios del dispositivo por employeeNo.
    Endpoint típico Hikvision:
    POST /ISAPI/AccessControl/UserInfo/Delete?format=json
    """
    url = f"http://{device_ip}/ISAPI/AccessControl/UserInfo/Delete?format=json"
    payload = {"UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": str(x)} for x in employee_nos]}}

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.put(
                url,
                json=payload,
                auth=httpx.DigestAuth(device_username, device_password),
                headers={"Content-Type": "application/json"},
            )
    except httpx.RequestError as e:
        raise HikvisionError(
            f"No se pudo conectar al dispositivo ({device_ip}): {e}",
            status=502,
            response=str(e)
        )

    if resp.status_code >= 400:
        raise HikvisionError(
            "Dispositivo rechazó borrado",
            status=resp.status_code,
            response=resp.text[:500],
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}

def register_user_face_on_device(
    *,
    device_ip: str,
    device_username: str,
    device_password: str,
    employee_no: str,
    image_path: str | Path,
    fdid: str = "1",
    face_lib_type: str = "blackFD",
    timeout_seconds: float = 20.0,
) -> dict:
    """
    Sube imagen de rostro al dispositivo y la asocia al FPID=employee_no.
    POST /ISAPI/Intelligent/FDLib/FaceDataRecord?format=json
    multipart:
      - FaceDataRecord: JSON string
      - FaceImage: binary
    """
    url = f"http://{device_ip}/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json"

    record = {
        "faceLibType": face_lib_type,
        "FDID": str(fdid),
        "FPID": str(employee_no),
    }

    image_path = Path(image_path)

    if not image_path.exists():
        raise HikvisionError(f"Imagen no existe: {image_path}")
    
    optimized_image_bytes = optimize_image_for_hikvision(image_path)

    content_type = (
        "image/jpeg"
        if image_path.suffix.lower() in [".jpg", ".jpeg"]
        else "image/png"
    )

    files = {
        "FaceDataRecord": (
            None,
            json.dumps(record),
            "application/json"
        ),
        "FaceImage": (
            image_path.name,
            optimized_image_bytes,
            content_type
        ),
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(
                url,
                files=files,
                auth=httpx.DigestAuth(device_username, device_password),
            )
    except httpx.RequestError as e:
        raise HikvisionError(
            f"No se pudo conectar al dispositivo ({device_ip}): {e}",
            status=502,
            response=str(e)
        )

    if resp.status_code >= 400:
        raise HikvisionError(
            "Dispositivo rechazó registro de rostro",
            status=resp.status_code,
            response=resp.text[:500],
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}

def update_user_face_on_device(
    *,
    device_ip: str,
    device_username: str,
    device_password: str,
    employee_no: str,
    image_path: str | Path,
    fdid: str = "1",
    face_lib_type: str = "blackFD",
    timeout_seconds: float = 20.0,
) -> dict:
    """
    Modifica la imagen de rostro ya existente para el FPID=employee_no.
    PUT /ISAPI/Intelligent/FDLib/FDModify?format=json
    multipart:
      - FaceDataRecord: JSON string
      - FaceImage: binary
    """
    url = f"http://{device_ip}/ISAPI/Intelligent/FDLib/FDModify?format=json"

    record = {
        "faceLibType": face_lib_type,
        "FDID": str(fdid),
        "FPID": str(employee_no),
    }

    image_path = Path(image_path)

    if not image_path.exists():
        raise HikvisionError(f"Imagen no existe: {image_path}")

    optimized_image_bytes = optimize_image_for_hikvision(image_path)

    content_type = (
        "image/jpeg"
        if image_path.suffix.lower() in [".jpg", ".jpeg"]
        else "image/png"
    )

    files = {
        "FaceDataRecord": (
            None,
            json.dumps(record),
            "application/json",
        ),
        "FaceImage": (
            image_path.name,
            optimized_image_bytes,
            content_type,
        ),
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.put(
                url,
                files=files,
                auth=httpx.DigestAuth(device_username, device_password),
            )

    except httpx.RequestError as e:
        raise HikvisionError(
            f"No se pudo conectar al dispositivo ({device_ip}): {e}",
            status=502,
            response=str(e),
        )

    if resp.status_code >= 400:
        raise HikvisionError(
            "Dispositivo rechazó actualización de rostro",
            status=resp.status_code,
            response=resp.text[:500],
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}