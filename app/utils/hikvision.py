import logging
from fastapi import HTTPException, status
from datetime import datetime
from app import models
from app.services.hikvision_service import (
    HikvisionError,
    build_user_payload,
    register_user_on_device,
    register_user_face_on_device,
    update_user_on_device,
    update_user_face_on_device,
    delete_user_from_device
)

def register_user_in_devices(
    *,
    user_db: models.User,
    devices: list[models.Device],
    valid_from: datetime,
    valid_to: datetime,
    logger: logging.Logger
) -> None:
    registered_on_devices: list[tuple[models.Device, str]] = []

    try:
        for device in devices:
            employee_no = f"{user_db.id}{device.id}"
            hik_payload = build_user_payload(
                employee_no=employee_no,
                name=user_db.name,
                begin_time=valid_from,
                end_time=valid_to,
                door_no=1,
                plan_template_no="1",
                include_user_type=True,
            )

            register_user_on_device(
                device_ip=device.ip_address,
                device_username=device.username,
                device_password=device.password,
                payload=hik_payload,
            )
            registered_on_devices.append((device, employee_no))
            logger.info(
                "User synced to device successfully user_id=%s device_id=%s employee_no=%s",
                user_db.id,
                device.id,
                employee_no,
            )

    except HikvisionError:
        for d_ok, emp_ok in registered_on_devices:
            try:
                delete_user_from_device(
                    device_ip=d_ok.ip_address,
                    device_username=d_ok.username,
                    device_password=d_ok.password,
                    employee_nos=[emp_ok],
                )
                logger.warning(
                    "Rollback performed in device for user_id=%s device_id=%s employee_no=%s",
                    user_db.id,
                    d_ok.id,
                    emp_ok,
                )
            except Exception:
                logger.exception(
                    "Failed rollback on device for user_id=%s device_id=%s employee_no=%s",
                    user_db.id,
                    d_ok.id,
                    emp_ok,
                )

        logger.exception("Failed to sync user_id=%s with biometric devices", user_db.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync user with biometric devices",
        )

def register_user_face_in_devices(
        devices: list[models.Device],
        user_id: int,
        image_path: str,
        logger: logging.Logger
):
    try:
        for device in devices:
            employee_no = f"{user_id}{device.id}"
            register_user_face_on_device(
                device_ip=device.ip_address,
                device_username=device.username,
                device_password=device.password,
                employee_no=employee_no,
                image_path=image_path,
            )
            logger.info(
                "User face synced to device successfully user_id=%s device_id=%s employee_no=%s",
                user_id,
                device.id,
                employee_no,
            )
    except HikvisionError as e:
        logger.error(
            "Failed to sync user face to device user_id=%s",
            user_id,
        )

        delete_user_in_devices(
            user_id=user_id,
            devices=devices,
            logger=logger,
        )

        raise HTTPException(
            status_code=e.status,
            detail="Failed to sync user face with biometric devices",
        )

def update_user_in_devices(
    *,
    user_id: int,
    name: str = None,
    begin_time: datetime = None,
    end_time: datetime = None,
    devices: list[models.Device],
    logger: logging.Logger
) -> None:
    
    for device in devices:
        try:
            employee_no = f"{user_id}{device.id}"
            
            hik_payload = build_user_payload(
                employee_no=employee_no,
                name=name,
                begin_time=begin_time,
                end_time=end_time,
            )

            update_user_on_device(
                device_ip=device.ip_address,
                device_username=device.username,
                device_password=device.password,
                payload=hik_payload,
            )
            logger.info(
                "User updated in device successfully user_id=%s device_id=%s employee_no=%s",
                user_id,
                device.id,
                employee_no,
            )
        except HikvisionError as e:
            logger.error(
                "Failed to update user in device user_id=%s device_id=%s",
                user_id,
                device.id,
            )
            raise HTTPException(
                status_code=e.status,
                detail=f"Error updating device {device.id} {e.response}",
            )

def update_user_face_in_devices(
    *,
    user_db: models.User,
    devices: list[models.Device],
    image_path: str,
    logger: logging.Logger
) -> None:
    try:
        for device in devices:
            employee_no = f"{user_db.id}{device.id}"
            update_user_face_on_device(
                device_ip=device.ip_address,
                device_username=device.username,
                device_password=device.password,
                employee_no=employee_no,
                image_path=image_path,
            )
            logger.info(
                "User face updated in device successfully user_id=%s device_id=%s employee_no=%s",
                user_db.id,
                device.id,
                employee_no,
            )
    except HikvisionError:
        logger.exception(
            "Failed to update user face in device user_id=%s",
            user_db.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to update user face with biometric devices",
        )

def delete_user_in_devices(
    *,
    user_id: int,
    devices: list[models.Device],
    logger: logging.Logger
) -> None:

    try:
        for device in devices:
            employee_no = f"{user_id}{device.id}"
            delete_user_from_device(
                device_ip=device.ip_address,
                device_username=device.username,
                device_password=device.password,
                employee_nos=[employee_no],
            )
            logger.info(
                "User deleted from device successfully user_id=%s device_id=%s employee_no=%s",
                user_id,
                device.id,
                employee_no,
            )

    except HikvisionError:
        logger.exception(
            "Failed to delete user from device user_id=%s device_id=%s",
            user_id,
            device.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not remove user from device {device.id}",
        )