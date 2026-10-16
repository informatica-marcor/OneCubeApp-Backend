from __future__ import annotations
from pathlib import Path
from typing import Optional, Any
from datetime import datetime
import logging
import resend

from app.core.config import settings

logger = logging.getLogger(__name__)

def build_email_template(body: str) -> str:
    return  f"""
    <div style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif; color:#222222;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
            style="background-color:#f4f6f8; margin:0; padding:0;">
            <tr>
                <td align="center" style="padding:24px 12px;">

                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                        style="max-width:640px; background-color:#ffffff; border-radius:18px; overflow:hidden; box-shadow:0 6px 20px rgba(0,0,0,0.08);">

                        <!-- Línea superior -->
                        <tr>
                            <td style="padding:0; margin:0;">
                                <div style="height:5px; background-color:#5FCD67; line-height:5px; font-size:5px;">&nbsp;
                                </div>
                            </td>
                        </tr>

                        <!-- Header -->
                        <tr>
                            <td style="background:#ffffff; padding:32px 32px 20px 32px; text-align:center;">

                                <p style="margin:0; font-size:13px; letter-spacing:2px; color:#5FCD67; font-weight:bold; text-transform:uppercase;">
                                  One Cube
                                </p>
                            </td>
                        </tr>

                        <!-- Contenido -->
                        <tr>
                            <td style="padding:12px 28px 28px 28px;">

                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td
                                            style="background-color:#f7faf8; border-radius:14px; padding:22px 20px; border:1px solid #e5efe7;">
                                            {body}
                                        </td>
                                    </tr>
                                </table>

                                <!-- Aviso automático -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                                    style="margin:22px 0 0 0;">
                                    <tr>
                                        <td
                                            style="background-color:#eef9f0; border-left:4px solid #5FCD67; border-radius:10px; padding:14px 16px;">
                                            <p style="margin:0; font-size:13px; line-height:1.6; color:#2f4f35;">
                                                Este es un mensaje automático, por favor no respondas a este correo.
                                            </p>
                                        </td>
                                    </tr>
                                </table>

                            </td>
                        </tr>

                        <!-- Separador -->
                        <tr>
                            <td style="padding:0 28px;">
                                <div style="height:1px; background-color:#e9ecef;"></div>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background-color:#1b1b1b; padding:28px 28px 0 28px;">
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td style="padding-bottom:16px;">
                                            <div
                                                style="font-size:18px; font-style:italic; font-weight:bold; color:#ffffff; margin:0 0 10px 0;">
                                                Inteligencia en Almacenaje
                                            </div>

                                            <div style="font-size:12px; color:#cfcfcf; line-height:1.6;">
                                                “El orden es la primera ley del éxito. Haz espacio para lo que viene.”
                                            </div>
                                        </td>
                                    </tr>
                                </table>

                                <!-- Línea verde al final del footer -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td style="padding:0; margin:0;">
                                            <div
                                                style="height:4px; background-color:#5FCD67; line-height:4px; font-size:4px;">
                                                &nbsp;</div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                    </table>

                </td>
            </tr>
        </table>
    </div>
    """


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: Optional[list[str]] = None,
) -> Optional[str]:

    resend.api_key = settings.resend_api_key

    email_attachments: list[resend.Attachment] = []
    
    for attachment_path in attachments or []:
        file_path = Path(attachment_path)

        if not file_path.is_file():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        file_content: bytes = file_path.read_bytes()

        attachment: resend.Attachment = {
            "content": list(file_content),
            "filename": file_path.name,
        }

        email_attachments.append(attachment)

    params: resend.Emails.SendParams = {
        "from": settings.email_address,
        "to": [to],
        "bcc": "notificaciones@onecube.cl",
        "subject": subject,
        "html": build_email_template(body),
    }

    if email_attachments:
        params["attachments"] = email_attachments

    return resend.Emails.send(params)


def _send_email(
    *,
    to_email: str,
    subject: str,
    html: str,
    email_type: str,
    attachments: Optional[list[dict[str, Any]]] = None,
) -> Optional[str]:
    if not settings.resend_api_key or not settings.email_address:
        logger.warning(
            "Email service not configured email_type=%s to_email=%s missing_resend_api_key=%s missing_email_address=%s",
            email_type,
            to_email,
            not bool(settings.resend_api_key),
            not bool(settings.email_address),
        )
        return None

    resend.api_key = settings.resend_api_key

    payload: dict[str, Any] = {
        "from": settings.email_address,
        "to": [to_email],
        "subject": subject,
        "bcc": "informatica@marcor.cl",
        "html": html,
    }

    if attachments:
        payload["attachments"] = attachments

    try:
        resp = resend.Emails.send(payload)

        email_id = resp.get("id") if isinstance(resp, dict) else None

        if email_id:
            logger.info(
                "Email sent successfully email_type=%s to_email=%s email_id=%s",
                email_type,
                to_email,
                email_id,
            )
        else:
            logger.warning(
                "Email provider response without id email_type=%s to_email=%s response_type=%s",
                email_type,
                to_email,
                type(resp).__name__,
            )

        return email_id

    except Exception:
        logger.exception(
            "Email sending failed email_type=%s to_email=%s",
            email_type,
            to_email,
        )
        return None


def send_login_code_email(
    *,
    to_email: str,
    code: str,
    expires_minutes: int
) -> Optional[str]:
    subject = "Código de inicio de sesión"

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Código de inicio de sesión</title>
      </head>
      <body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif; color:#222222;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f4f6f8; margin:0; padding:0;">
          <tr>
            <td align="center" style="padding:24px 12px;">

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px; background-color:#ffffff; border-radius:18px; overflow:hidden; box-shadow:0 6px 20px rgba(0,0,0,0.08);">

                <!-- Header -->
                <tr>
                  <td style="background:#ffffff; padding:32px 32px 20px 32px; text-align:center;">
                    <p style="margin:0; font-size:13px; letter-spacing:2px; color:#5FCD67; font-weight:bold; text-transform:uppercase;">
                      One Cube
                    </p>
                    <h1 style="margin:10px 0 0 0; font-size:26px; line-height:1.2; color:#111111;">
                      Tu código de acceso
                    </h1>
                    <p style="margin:10px 0 0 0; font-size:14px; line-height:1.6; color:#666666;">
                      Usa este código para iniciar sesión de forma segura.
                    </p>
                  </td>
                </tr>

                <!-- Contenido -->
                <tr>
                  <td style="padding:12px 28px 24px 28px;">

                    <!-- Código -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 22px 0;">
                      <tr>
                        <td align="center" style="background-color:#f7faf8; border:2px dashed #5FCD67; border-radius:14px; padding:22px 12px;">
                          <div style="font-size:34px; font-weight:700; letter-spacing:8px; color:#1a1a1a;">
                            {code}
                          </div>
                        </td>
                      </tr>
                    </table>

                    <!-- Aviso -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 22px 0;">
                      <tr>
                        <td style="background-color:#eef9f0; border-left:4px solid #5FCD67; border-radius:10px; padding:14px 16px;">
                          <p style="margin:0; font-size:14px; line-height:1.6; color:#2f4f35;">
                            Este código expira en <strong>{expires_minutes} minutos</strong>.
                          </p>
                        </td>
                      </tr>
                    </table>

                    <p style="margin:0 0 10px 0; font-size:14px; line-height:1.7; color:#666666;">
                      Si no solicitaste este inicio de sesión, puedes ignorar este correo.
                    </p>

                    <p style="margin:0; font-size:12px; line-height:1.7; color:#8a8a8a;">
                      Este es un mensaje automático, por favor no respondas a este correo.
                    </p>
                  </td>
                </tr>

                <!-- Separador -->
                <tr>
                  <td style="padding:0 28px;">
                    <div style="height:1px; background-color:#e9ecef;"></div>
                  </td>
                </tr>

                <!-- Footer -->
                <tr>
                  <td style="background-color:#1b1b1b; padding:28px 28px 0 28px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding-bottom:16px;">
                          <div style="font-size:18px; font-style:italic; font-weight:bold; color:#ffffff; margin:0 0 10px 0;">
                            Inteligencia en Almacenaje
                          </div>
                          <div style="font-size:12px; color:#cfcfcf; line-height:1.6;">
                            “El orden es la primera ley del éxito. Haz espacio para lo que viene.”
                          </div>
                        </td>
                      </tr>
                    </table>

                    <!-- Línea verde al final del footer -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding:0; margin:0;">
                          <div style="height:4px; background-color:#5FCD67; line-height:4px; font-size:4px;">&nbsp;</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

              </table>

            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    return _send_email(
        to_email=to_email,
        subject=subject,
        html=html,
        email_type="login_code",
    )


def send_temporary_access_granted_email(
    *,
    to_email: str,
    user_name: str,
    start_date: datetime,
    end_date: datetime,
) -> Optional[str]:
    subject = "Tu acceso temporal fue habilitado"

    start_label = start_date.strftime("%d-%m-%Y %H:%M")
    end_label = end_date.strftime("%d-%m-%Y %H:%M")

    html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
      <h2>Acceso temporal habilitado</h2>

      <p>Hola <b>{user_name}</b>,</p>

      <p>Te informamos que tu permiso de acceso fue creado correctamente.</p>

      <p>
        <b>Inicio de acceso:</b> {start_label}<br>
        <b>Término de acceso:</b> {end_label}
      </p>

      <p style="margin-top: 20px;">
          Si tienes dudas sobre tu acceso, por favor
          <a href="https://wa.me/56959508074" style="color: #25D366; font-weight: bold; text-decoration: none;">
            contacta al administrador vía WhatsApp
          </a>.
      </p>

      <p style="color: #666; font-size: 12px;">
        Este es un mensaje automático, por favor no respondas este correo.
      </p>
    </div>
    """

    return _send_email(
        to_email=to_email,
        subject=subject,
        html=html,
        email_type="temporary_access_granted",
    )


def send_portal_access_enabled_email(
    *,
    to_email: str,
    user_name: str,
) -> Optional[str]:
    subject = "Ya puedes ingresar al portal de clientes OneCube"

    html = f"""
      <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #222; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #0056b3;">Acceso habilitado al portal OneCube</h2>

        <p>Te damos la bienvenida <b>{user_name}</b>,</p>

        <p>
          Te informamos que al contratar tu bodega tienes acceso al portal <b>OneCube</b>. 
          Desde este momento puedes ingresar utilizando tu correo electrónico para iniciar sesión en
          <a href="https://onecube.cl/" style="color: #25D366; font-weight: bold; text-decoration: none;">
            Clientes OneCube.
          </a>
        </p>

        <div style="background-color: #f9f9f9; padding: 15px; border-radius: 8px; border-left: 4px solid #0056b3;">
          <p style="margin-top: 0;"><b>¿Qué puedes hacer en el portal?</b></p>
          <ul style="margin-bottom: 0;">
            <li>Revisar la información detallada de tus <b>bodegas contratadas</b>.</li>
            <li>Subir tu foto para pasar por los puntos de control biométrico</b>.</li>
            <li>Gestionar y dar <b>acceso a terceros</b> para ingresar por los puntos de control biométrico.</li>
            <li>Levantar <b>tickets de ayuda</b> para soporte técnico o comercial.</li>
          </ul>
        </div>

        <p style="margin-top: 20px;">
          Si tienes problemas para acceder o no reconoces este mensaje, por favor 
          <a href="https://wa.me/56959508074" style="color: #25D366; font-weight: bold; text-decoration: none;">
            contacta al administrador vía WhatsApp
          </a>.
        </p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

        <p style="color: #666; font-size: 12px; text-align: center;">
          Este es un mensaje automático generado por el sistema, por favor no respondas a este correo.
        </p>
      </div>
      """

    return _send_email(
        to_email=to_email,
        subject=subject,
        html=html,
        email_type="portal_access_enabled",
    )


def send_payment_due_notification(
    *,
    to_email: str,
    user_name: str,
    due_date: Optional[datetime] = None,
) -> Optional[str]:
    subject = "Recordatorio de pago de arriendo OneCube"

    due_date_label = (
        due_date.strftime("%d-%m-%Y")
        if due_date
        else "correspondiente al periodo actual"
    )

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Recordatorio de pago</title>
      </head>

      <body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif; color:#222222;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f4f6f8; margin:0; padding:0;">
          <tr>
            <td align="center" style="padding:24px 12px;">

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px; background-color:#ffffff; border-radius:18px; overflow:hidden; box-shadow:0 6px 20px rgba(0,0,0,0.08);">

                <!-- Header -->
                <tr>
                  <td style="background:#ffffff; padding:32px 32px 20px 32px; text-align:center;">
                    <p style="margin:0; font-size:13px; letter-spacing:2px; color:#5FCD67; font-weight:bold; text-transform:uppercase;">
                      One Cube
                    </p>

                    <h1 style="margin:10px 0 0 0; font-size:26px; line-height:1.2; color:#111111;">
                      Recordatorio de pago
                    </h1>

                    <p style="margin:10px 0 0 0; font-size:14px; line-height:1.6; color:#666666;">
                      Te recordamos que corresponde realizar el pago de tu arriendo.
                    </p>
                  </td>
                </tr>

                <!-- Contenido -->
                <tr>
                  <td style="padding:12px 28px 24px 28px;">

                    <p style="margin:0 0 14px 0; font-size:15px; line-height:1.7; color:#333333;">
                      Hola <strong>{user_name}</strong>,
                    </p>

                    <p style="margin:0 0 16px 0; font-size:14px; line-height:1.7; color:#555555;">
                      Junto con saludarte, te informamos que hoy se cumple la fecha de pago
                      <strong>{due_date_label}</strong> asociada a tu arriendo en <strong>One Cube</strong>.
                    </p>

                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 20px 0;">
                      <tr>
                        <td style="background-color:#eef9f0; border-left:4px solid #5FCD67; border-radius:10px; padding:14px 16px;">
                          <p style="margin:0; font-size:14px; line-height:1.6; color:#2f4f35;">
                            Si ya realizaste el pago, puedes ignorar este mensaje.
                            En caso contrario, te solicitamos regularizarlo dentro del plazo correspondiente.
                          </p>
                        </td>
                      </tr>
                    </table>

                    <p style="margin:0 0 16px 0; font-size:14px; line-height:1.7; color:#555555;">
                      Si tienes dudas sobre el pago, tu contrato o necesitas asistencia,
                      puedes contactar al administrador.
                    </p>

                    <p style="margin:0 0 18px 0; font-size:14px; line-height:1.7;">
                      <a href="https://wa.me/56959508074" style="color:#25D366; font-weight:bold; text-decoration:none;">
                        Contactar al administrador vía WhatsApp
                      </a>
                    </p>

                    <p style="margin:0; font-size:12px; line-height:1.7; color:#8a8a8a;">
                      Este es un mensaje automático, por favor no respondas a este correo.
                    </p>
                  </td>
                </tr>

                <!-- Separador -->
                <tr>
                  <td style="padding:0 28px;">
                    <div style="height:1px; background-color:#e9ecef;"></div>
                  </td>
                </tr>

                <!-- Footer -->
                <tr>
                  <td style="background-color:#1b1b1b; padding:28px 28px 0 28px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding-bottom:16px;">
                          <div style="font-size:18px; font-style:italic; font-weight:bold; color:#ffffff; margin:0 0 10px 0;">
                            Inteligencia en Almacenaje
                          </div>

                          <div style="font-size:12px; color:#cfcfcf; line-height:1.6;">
                            “El orden es la primera ley del éxito. Haz espacio para lo que viene.”
                          </div>
                        </td>
                      </tr>
                    </table>

                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding:0; margin:0;">
                          <div style="height:4px; background-color:#5FCD67; line-height:4px; font-size:4px;">&nbsp;</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

              </table>

            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    return _send_email(
        to_email=to_email,
        subject=subject,
        html=html,
        email_type="payment_due_notification",
    )


def send_lease_ending_soon_notification(
    *,
    to_email: str,
    user_name: str,
    lease_end_date: datetime,
) -> Optional[str]:
    formatted_end_date = lease_end_date.strftime("%d-%m-%Y")

    subject = "Tu contrato está próximo a finalizar"

    html = f"""
    <div style="font-family: Arial, sans-serif; color: #222; line-height: 1.5;">
        <h2>Hola {user_name},</h2>

        <p>
            Te informamos que tu contrato de arriendo está próximo a finalizar.
        </p>

        <p>
            La fecha de término registrada es:
            <strong>{formatted_end_date}</strong>.
        </p>

        <p>
            Si deseas continuar con el arriendo, existe la posibilidad de extender
            el contrato mediante un anexo.
        </p>

        <p>
            Para gestionar la extensión, por favor comunícate con nuestro equipo
            antes de la fecha de término.
        </p>

        <p>
            Saludos,<br />
            Equipo One Cube
        </p>
    </div>
    """
    
    email_id = _send_email(
        to_email=to_email,
        subject=subject,
        html=html,
    )

    return email_id