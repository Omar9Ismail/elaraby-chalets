import os
import sys
import shutil
import base64
import hashlib
import hmac
import datetime
import subprocess
import threading
import smtplib
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import tkinter as tk
from tkinter import filedialog
import webview

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

BUNDLE_DIR = getattr(sys, '_MEIPASS', APP_DIR)

# مسار التخزين المحمي في بارتيشن C
APPDATA_BASE = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~\\AppData\\Local')
DATA_FOLDER = os.path.join(APPDATA_BASE, 'ElarabyProCloudData')
AUTO_BACKUP_DIR = os.path.join(DATA_FOLDER, 'AutoBackups')
TEMP_SHARE_DIR = os.path.join(DATA_FOLDER, 'TempWhatsAppShare')
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)
os.makedirs(TEMP_SHARE_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_FOLDER, 'elaraby_cloud_cache.enc')
LOGO_BUNDLED = os.path.join(BUNDLE_DIR, 'Elaraby.png')
LOGO_EXTERNAL = os.path.join(APP_DIR, 'Elaraby.png')

SECRET_KEY = b"ELARABY_REAL_ESTATE_SUEZ_2026_SECURE_KEY"

def _keystream(salt: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(SECRET_KEY + salt + counter.to_bytes(4, 'big')).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])

def encrypt_text(plain_text: str) -> bytes:
    raw = plain_text.encode('utf-8')
    salt = os.urandom(16)
    ks = _keystream(salt, len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, ks))
    sig = hmac.new(SECRET_KEY, salt + cipher, hashlib.sha256).digest()
    return base64.b64encode(b"ELARABY_ENC_V1" + salt + sig + cipher)

def decrypt_bytes(encoded_bytes: bytes) -> str:
    blob = base64.b64decode(encoded_bytes)
    header = b"ELARABY_ENC_V1"
    if not blob.startswith(header):
        raise ValueError("صيغة الملف غير صالحة")
    idx = len(header)
    salt = blob[idx:idx+16]
    sig = blob[idx+16:idx+48]
    cipher = blob[idx+48:]
    expected_sig = hmac.new(SECRET_KEY, salt + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("الملف تالف أو مفتاح التشفير غير مطابق")
    ks = _keystream(salt, len(cipher))
    raw = bytes(a ^ b for a, b in zip(cipher, ks))
    return raw.decode('utf-8')

def create_daily_auto_backup(encrypted_bytes: bytes):
    try:
        today_str = datetime.date.today().isoformat()
        backup_path = os.path.join(AUTO_BACKUP_DIR, f"AutoBackup_{today_str}.elaraby")
        with open(backup_path, 'wb') as f:
            f.write(encrypted_bytes)
        files = sorted([os.path.join(AUTO_BACKUP_DIR, x) for x in os.listdir(AUTO_BACKUP_DIR) if x.endswith('.elaraby')])
        while len(files) > 7:
            os.remove(files.pop(0))
    except Exception:
        pass

class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BUNDLE_DIR, **kwargs)
    def log_message(self, format, *args):
        pass



def start_local_server():
    server = HTTPServer(('127.0.0.1', 0), QuietHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return port

class UnifiedDesktopAPI:
    def get_logo_base64(self):
        target_logo = LOGO_EXTERNAL if os.path.exists(LOGO_EXTERNAL) else LOGO_BUNDLED
        if os.path.exists(target_logo):
            try:
                with open(target_logo, 'rb') as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    return "data:image/png;base64," + encoded
            except Exception:
                return ""
        return ""

    def save_chalet_images_dialog(self, items):
        try:
            import base64, os, re, webview
            if not items:
                return {"success": False, "error": "لا توجد صور للحفظ"}

            window = webview.windows[0]
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            if not result or len(result) == 0:
                return {"success": False, "cancelled": True}

            target_dir = result[0]
            saved_count = 0

            for item in items:
                file_name = item.get("fileName", f"chalet_{saved_count + 1}.jpg")
                data_url = item.get("dataUrl", "")
                if not data_url or "," not in data_url:
                    continue

                b64_data = data_url.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_data)

                safe_name = re.sub(r'[\\/*?:"<>|]', "_", str(file_name)).strip()
                out_path = os.path.join(target_dir, safe_name)

                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                saved_count += 1

            return {"success": True, "count": saved_count, "folder": target_dir}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def load_data(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, 'rb') as f:
                    encrypted_bytes = f.read()
                    if encrypted_bytes:
                        return decrypt_bytes(encrypted_bytes)
            except Exception:
                return ""
        return ""

    def save_data(self, json_str):
        try:
            os.makedirs(DATA_FOLDER, exist_ok=True)
            encrypted_bytes = encrypt_text(json_str)
            with open(DB_FILE, 'wb') as f:
                f.write(encrypted_bytes)
                f.flush()
                os.fsync(f.fileno())
            create_daily_auto_backup(encrypted_bytes)
            return True
        except Exception:
            return False

    def export_encrypted_full_backup(self, default_filename, current_json_str):
        try:
            self.save_data(current_json_str)
            encrypted_bytes = encrypt_text(current_json_str)

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.asksaveasfilename(
                initialdir=os.path.expanduser('~/Desktop'),
                initialfile=default_filename,
                defaultextension=".elaraby",
                filetypes=[("Elaraby Encrypted Backup", "*.elaraby"), ("All Files", "*.*")]
            )
            root.destroy()
            if file_path:
                with open(file_path, 'wb') as f:
                    f.write(encrypted_bytes)
                return {"success": True, "path": file_path}
            return {"success": False, "cancelled": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def import_encrypted_full_backup(self):
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(
                initialdir=os.path.expanduser('~/Desktop'),
                title="اختر ملف النسخة الاحتياطية المشفرة (.elaraby)",
                filetypes=[("Elaraby Encrypted Backup", "*.elaraby"), ("All Files", "*.*")]
            )
            root.destroy()
            if not file_path:
                return {"success": False, "cancelled": True}

            with open(file_path, 'rb') as f:
                raw_bytes = f.read()

            decrypted_json = decrypt_bytes(raw_bytes)
            self.save_data(decrypted_json)
            return {"success": True, "data": decrypted_json}
        except Exception:
            return {"success": False, "error": "الملف تالف أو غير صالح!"}

    def open_data_folder(self):
        try:
            os.makedirs(DATA_FOLDER, exist_ok=True)
            os.startfile(DATA_FOLDER)
            return {"success": True, "path": DATA_FOLDER}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_text_file(self, default_filename, content, file_types):
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.asksaveasfilename(
                initialdir=os.path.expanduser('~/Desktop'),
                initialfile=default_filename,
                defaultextension=".csv",
                filetypes=[("Excel CSV", "*.csv"), ("All Files", "*.*")]
            )
            root.destroy()
            if file_path:
                with open(file_path, 'w', encoding='utf-8-sig') as f:
                    f.write(content)
                return {"success": True, "path": file_path}
            return {"success": False, "cancelled": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_base64_image(self, default_filename, base64_data):
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            ext = ".jpg" if ".jpg" in default_filename else ".png"
            file_path = filedialog.asksaveasfilename(
                initialdir=os.path.expanduser('~/Desktop'),
                initialfile=default_filename,
                defaultextension=ext,
                filetypes=[("Image Files", f"*{ext}"), ("All Files", "*.*")]
            )
            root.destroy()
            if file_path:
                header, encoded = base64_data.split(",", 1)
                with open(file_path, 'wb') as f:
                    f.write(base64.b64decode(encoded))
                return {"success": True, "path": file_path}
            return {"success": False, "cancelled": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def copy_images_to_clipboard_and_whatsapp(self, images_base64_list, message_text, target_phone=""):
        try:
            for old_f in os.listdir(TEMP_SHARE_DIR):
                try:
                    os.remove(os.path.join(TEMP_SHARE_DIR, old_f))
                except Exception:
                    pass

            saved_paths = []
            for idx, b64 in enumerate(images_base64_list):
                header, encoded = b64.split(",", 1)
                ext = "png" if "image/png" in header else "jpg"
                img_path = os.path.join(TEMP_SHARE_DIR, f"Elaraby_Share_{idx + 1}.{ext}")
                with open(img_path, 'wb') as f:
                    f.write(base64.b64decode(encoded))
                saved_paths.append(img_path)

            if saved_paths:
                ps_paths = ",".join([f"'{p}'" for p in saved_paths])
                ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; $col = New-Object System.Collections.Specialized.StringCollection; $col.AddRange(@({ps_paths})); [System.Windows.Forms.Clipboard]::SetFileDropList($col)"
                subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd], check=False)

            encoded_msg = urllib.parse.quote(message_text)
            clean_phone = "".join(filter(str.isdigit, target_phone))
            if clean_phone.startswith("01") and len(clean_phone) == 11:
                clean_phone = "2" + clean_phone

            if clean_phone:
                wa_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"
            else:
                wa_url = f"https://api.whatsapp.com/send?text={encoded_msg}"

            os.startfile(wa_url)
            return {"success": True, "count": len(saved_paths)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_booking_gmail(self, gmail_config, booking_data, action_title="حجز جديد مؤكد"):
        sender = (gmail_config.get("sender") or "").strip()
        app_pass = (gmail_config.get("appPassword") or "").replace(" ", "").strip()
        recipient = (gmail_config.get("recipient") or sender).strip()

        if not sender or not app_pass or not recipient:
            return {"success": False, "skipped": True}

        def _worker():
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"✅ {action_title} #{booking_data['id']} | {booking_data['village']} ({booking_data['chaletName']}) - {booking_data['clientName']}"
                msg["From"] = f"نظام حجز شاليهات العربي <{sender}>"
                msg["To"] = recipient

                actor = booking_data.get('createdBy') or booking_data.get('agentName', '')
                html_body = f"""
                <div dir="rtl" style="font-family: Tahoma, Arial, sans-serif; max-width: 560px; margin: auto; border: 2px solid #0f766e; border-radius: 12px; overflow: hidden;">
                  <div style="background: #0f172a; color: #fef08a; padding: 16px 20px; text-align: center;">
                    <h2 style="margin:0;">شركة العربي للاستثمار العقاري</h2>
                    <p style="margin:4px 0 0; color:#ccfbf1; font-size:13px;">{action_title} (#{booking_data['id']})</p>
                  </div>
                  <div style="padding: 18px 22px; background: #ffffff; color: #0f172a;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                      <tr><td style="padding:8px; border-bottom:1px solid #eee; color:#64748b;"><b>القرية / الشاليه:</b></td><td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold;">{booking_data['village']} - {booking_data['chaletName']}</td></tr>
                      <tr><td style="padding:8px; border-bottom:1px solid #eee; color:#64748b;"><b>اسم العميل:</b></td><td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold;">{booking_data['clientName']}</td></tr>
                      <tr><td style="padding:8px; border-bottom:1px solid #eee; color:#64748b;"><b>رقم الهاتف:</b></td><td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold;">{booking_data['clientPhone']}</td></tr>
                      <tr><td style="padding:8px; border-bottom:1px solid #eee; color:#64748b;"><b>فترة الإقامة:</b></td><td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold;">من {booking_data['startDate']} إلى {booking_data['endDate']} ({booking_data['rentType']})</td></tr>
                      <tr><td style="padding:8px; border-bottom:1px solid #eee; color:#64748b;"><b>نُفذ بواسطة اليوزر:</b></td><td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold; color:#0f766e;">{actor}</td></tr>
                    </table>
                    <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-radius: 8px; padding: 12px; margin-top: 14px;">
                      <p style="margin:4px 0;"><b>💰 الإجمالي الكلي:</b> {booking_data['total']:,} ج.م</p>
                      <p style="margin:4px 0; color:#15803d;"><b>💵 إجمالي المدفوع ({booking_data['method']}):</b> {booking_data['deposit']:,} ج.م</p>
                      <p style="margin:4px 0; color:#dc2626; font-size:16px;"><b>⏳ المتبقي عند الدخول:</b> {booking_data['remaining']:,} ج.م</p>
                    </div>
                  </div>
                </div>
                """
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                    server.login(sender, app_pass)
                    server.sendmail(sender, [recipient], msg.as_string())
            except Exception as ex:
                print("Gmail error:", ex)

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "queued": True}

HOSTED_URL = 'https://omar9ismail.github.io/elaraby-chalets/'


def pick_start_url(local_port):
    # يحاول يفتح النسخة المنشورة الأول (عشان أي تحديث يوصل فورًا)،
    # ولو مفيش نت يرجع للنسخة المدمجة جوه البرنامج (أوفلاين).
    try:
        import urllib.request
        req = urllib.request.Request(HOSTED_URL, method='HEAD')
        urllib.request.urlopen(req, timeout=4)
        return HOSTED_URL
    except Exception:
        return f'http://127.0.0.1:{local_port}/index.html'


if __name__ == '__main__':
    port = start_local_server()
    api = UnifiedDesktopAPI()
    window = webview.create_window(
        title='نظام إدارة الحجوزات والخزينة وكتالوج الشاليهات - شركة العربي للاستثمار العقاري',
        url=pick_start_url(port),
        js_api=api,
        width=1380,
        height=780,
        min_size=(1050, 660)
    )
    webview.start()
