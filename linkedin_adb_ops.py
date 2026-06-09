#!/usr/bin/env python3
import argparse
import random
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

UI_REMOTE = "/sdcard/window_dump.xml"
UI_LOCAL = Path("./ui_linkedin.xml")


def run(cmd, check=True, capture=True):
    p = subprocess.run(cmd, text=True, capture_output=capture)
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr or p.stdout}")
    return p.stdout.strip() if capture else ""


def sleep_human(a=0.5, b=1.6):
    time.sleep(random.uniform(a, b))


def adb(*args, check=True, capture=True):
    return run(["adb", *args], check=check, capture=capture)


def ensure_device():
    out = adb("devices")
    lines = [l for l in out.splitlines()[1:] if l.strip()]
    ok = [l for l in lines if l.endswith("\tdevice")]
    if not ok:
        raise RuntimeError("No hay dispositivo ADB en estado 'device'.")


def open_linkedin():
    adb("shell", "am", "start", "-n", "com.linkedin.android/.infra.navigation.MainActivity")
    sleep_human()


def open_url(url):
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    sleep_human()


def focused_app():
    out = adb("shell", "dumpsys", "window")
    lines = [l for l in out.splitlines() if "mCurrentFocus" in l or "mFocusedApp" in l]
    return "\n".join(lines[-4:])


def ensure_linkedin_focus():
    focus = focused_app().lower()
    if "linkedin" not in focus and "chrome" not in focus:
        raise RuntimeError(f"LinkedIn no está en foco.\n{focus}")


def dump_ui(local_path=UI_LOCAL):
    adb("shell", "uiautomator", "dump", UI_REMOTE)
    adb("pull", UI_REMOTE, str(local_path))
    return local_path


def parse_bounds(bounds):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def iter_nodes(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for n in root.iter("node"):
        yield n


def find_node(xml_path, text_contains=None, desc_contains=None, resource_id_contains=None):
    text_contains = (text_contains or "").lower()
    desc_contains = (desc_contains or "").lower()
    rid_contains = (resource_id_contains or "").lower()

    for n in iter_nodes(xml_path):
        t = (n.attrib.get("text") or "").lower()
        d = (n.attrib.get("content-desc") or "").lower()
        rid = (n.attrib.get("resource-id") or "").lower()

        if text_contains and text_contains in t:
            return n
        if desc_contains and desc_contains in d:
            return n
        if rid_contains and rid_contains in rid:
            return n
    return None


def tap_node(node):
    center = parse_bounds(node.attrib.get("bounds", ""))
    if not center:
        return False
    x, y = center
    adb("shell", "input", "tap", str(x), str(y))
    sleep_human()
    return True


def tap_text(target):
    xml = dump_ui()
    node = find_node(xml, text_contains=target)
    if not node:
        return False
    return tap_node(node)


def tap_desc(target):
    xml = dump_ui()
    node = find_node(xml, desc_contains=target)
    if not node:
        return False
    return tap_node(node)


def tap_resource(rid_substring):
    xml = dump_ui()
    node = find_node(xml, resource_id_contains=rid_substring)
    if not node:
        return False
    return tap_node(node)


def type_text(text):
    safe = text.replace(" ", "%s")
    adb("shell", "input", "text", safe)
    sleep_human()


def keyevent(code):
    adb("shell", "input", "keyevent", str(code))
    sleep_human()


def post_text(message, mentions):
    open_linkedin()
    ensure_linkedin_focus()

    if not (tap_text("Publicar") or tap_desc("Publicar") or tap_resource("share_compose")):
        raise RuntimeError("No se pudo abrir el composer de publicación.")

    if not tap_resource("share_compose_text_input_entities"):
        # fallback: tap central
        adb("shell", "input", "tap", "540", "900")
        sleep_human()

    type_text(message)

    for m in mentions:
        type_text(" @" + m)
        sleep_human(0.8, 1.8)
        # intentar seleccionar sugerencia
        if not tap_resource("typeahead_result_container"):
            tap_text(m)

    if not (tap_resource("share_compose_post_button") or tap_text("Publicar")):
        raise RuntimeError("No se encontró botón de publicar.")

    print("OK: publicación enviada")


def post_photo(message):
    open_linkedin()
    ensure_linkedin_focus()

    if not (tap_text("Publicar") or tap_desc("Publicar") or tap_resource("share_compose")):
        raise RuntimeError("No se pudo abrir el composer.")

    # abrir fotos/galería
    if not (tap_text("Foto") or tap_text("Fotos") or tap_desc("Foto") or tap_resource("media")):
        raise RuntimeError("No se encontró botón de foto/galería.")

    sleep_human(1.0, 2.0)
    # seleccionar primera imagen visible
    if not tap_resource("image"):
        adb("shell", "input", "tap", "180", "520")
        sleep_human()

    # confirmar selección
    tap_text("Siguiente") or tap_text("Listo") or tap_text("Aceptar")

    if not tap_resource("share_compose_text_input_entities"):
        adb("shell", "input", "tap", "540", "900")
        sleep_human()
    type_text(message)

    if not (tap_resource("share_compose_post_button") or tap_text("Publicar")):
        raise RuntimeError("No se encontró botón Publicar.")

    print("OK: publicación con foto enviada")


def send_dm(profile_or_messaging_url, text):
    open_url(profile_or_messaging_url)
    ensure_linkedin_focus()

    # intentar desde botón mensaje
    if not (tap_text("Mensaje") or tap_desc("Mensaje") or tap_resource("message")):
        # si no, abrir mensajería
        open_url("https://www.linkedin.com/messaging/")

    sleep_human(1.0, 2.0)

    # detectar bloqueo premium/inmail
    xml = dump_ui()
    blob = Path(xml).read_text(encoding="utf-8", errors="ignore").lower()
    if "inmail" in blob or "premium" in blob:
        raise RuntimeError("DM bloqueado por Premium/InMail en esta vista.")

    # foco en caja y enviar
    if not (tap_resource("message_composer") or tap_resource("compose") or tap_text("Escribe un mensaje")):
        adb("shell", "input", "tap", "540", "2140")
        sleep_human()

    type_text(text)
    if not (tap_text("Enviar") or tap_desc("Enviar")):
        keyevent(66)

    print("OK: DM enviado")


def connect(profile_url):
    open_url(profile_url)
    ensure_linkedin_focus()

    if tap_text("Pendiente"):
        print("SKIP: ya estaba pendiente")
        return

    # intento directo
    if tap_text("Conectar") or tap_desc("Conectar"):
        tap_text("Enviar") or tap_text("Enviar sin nota")
        print("OK: solicitud enviada")
        return

    # fallback menú
    if tap_text("Más") or tap_desc("Más") or tap_desc("Más opciones"):
        if tap_text("Conectar"):
            tap_text("Enviar") or tap_text("Enviar sin nota")
            print("OK: solicitud enviada (fallback)")
            return

    raise RuntimeError("No se encontró opción Conectar.")


def cmd_check(_):
    ensure_device()
    open_linkedin()
    print("OK: dispositivo y LinkedIn accesibles")
    print(focused_app())


def main():
    parser = argparse.ArgumentParser(description="Operaciones LinkedIn por ADB")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("check", help="Valida ADB + foco LinkedIn")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("connect", help="Enviar solicitud de conexión")
    s.add_argument("--profile-url", required=True)
    s.set_defaults(func=lambda a: connect(a.profile_url))

    s = sub.add_parser("dm", help="Enviar DM")
    s.add_argument("--url", required=True, help="URL de perfil o messaging")
    s.add_argument("--text", required=True)
    s.set_defaults(func=lambda a: send_dm(a.url, a.text))

    s = sub.add_parser("post-text", help="Publicar texto")
    s.add_argument("--message", required=True)
    s.add_argument("--mention", action="append", default=[], help="Mención sin @; repetir flag para varias")
    s.set_defaults(func=lambda a: post_text(a.message, a.mention))

    s = sub.add_parser("post-photo", help="Publicar foto + texto")
    s.add_argument("--message", required=True)
    s.set_defaults(func=lambda a: post_photo(a.message))

    args = parser.parse_args()
    try:
        ensure_device()
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
