import os
import time
import imaplib
import email
import re
import requests
from datetime import datetime, timedelta, timezone
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. TG 通知功能 (带截图上传)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "❌"
    formatted_msg = f"{emoji} **Pella 自动化报告**\n━━━━━━━━━━━━━━━━━━\n👤 **账户**: `{os.environ.get('PELLA_EMAIL')}`\n📡 **状态**: {status}\n📝 **详情**: {message}\n🕒 **北京时间**: `{bj_time}`\n━━━━━━━━━━━━━━━━━━"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", 
                              data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, 
                              files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'})
    except Exception as e: logger.error(f"TG通知失败: {e}")

# ==========================================
# 2. Gmail 验证码提取 (严格搜寻未读)
# ==========================================
def get_pella_code(mail_address, app_password):
    logger.info(f"📡 正在连接 Gmail (IMAP)... 账户: {mail_address}")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(mail_address, app_password)
        mail.select("inbox")
        for i in range(10):
            logger.info(f"🔍 扫描未读邮件 (第 {i+1}/10 次尝试)...")
            status, messages = mail.search(None, '(FROM "Pella" UNSEEN)')
            if status == "OK" and messages[0]:
                latest_msg_id = messages[0].split()[-1]
                status, data = mail.fetch(latest_msg_id, "(RFC822)")
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            content = part.get_payload(decode=True).decode()
                else:
                    content = msg.get_payload(decode=True).decode()
                code = re.search(r'\b\d{6}\b', content)
                if code:
                    mail.store(latest_msg_id, '+FLAGS', '\\Seen')
                    return code.group()
            time.sleep(10)
        return None
    except Exception as e:
        logger.error(f"❌ 邮件读取异常: {e}")
        return None

# ==========================================
# 3. Pella 自动化流程 (保活与时间提取)
# ==========================================
def run_test():
    email_addr = os.environ.get("PELLA_EMAIL")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    
    with SB(uc=True, xvfb=True) as sb:
        try:
            # --- 第一阶段: 登录 ---
            logger.info("第一步: 访问 Pella 登录页")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 10)
            sb.sleep(8)
            sb.uc_gui_click_captcha()

            logger.info(f"第二步: 填入邮箱 {email_addr}")
            sb.wait_for_element_visible("#identifier-field", timeout=25)
            for char in email_addr:
                sb.add_text("#identifier-field", char)
                time.sleep(0.1)
            sb.press_keys("#identifier-field", "\n")
            sb.sleep(5)
            if sb.is_element_visible("#identifier-field"):
                sb.js_click('button:contains("Continue")')

            # --- 第二阶段: 验证码 ---
            logger.info("第三步: 启动 Gmail 抓取进程...")
            auth_code = get_pella_code(email_addr, app_pw)
            if not auth_code:
                raise Exception("未收到新验证码，请检查 Pella 是否因频率限制未发送")

            otp_selector = 'input[data-input-otp="true"]'
            sb.wait_for_element_visible(otp_selector, timeout=20)
            sb.type(otp_selector, auth_code)
            sb.sleep(10)

            # --- 第三阶段: 保活与提取时间 ---
            logger.info("第四步: 执行 Pella 内部续期动作...")
            # 1. 点击项目 nztz
            sb.wait_for_element_visible('div:contains("nztz")', timeout=30)
            sb.click('div:contains("nztz")')
            sb.sleep(5)
            
            # 2. 提取到期时间 (兼容 天/小时/分钟)
            expiry_info = "获取失败"
            try:
                full_text = sb.get_text('div.max-h-full.overflow-auto')
                # 正则匹配 1天22小时28分钟 这种格式
                match = re.search(r'(?:(\d+)\s*天)?\s*(?:(\d+)\s*小时)?\s*(?:(\d+)\s*分钟)?', full_text)
                if match:
                    parts = []
                    if match.group(1): parts.append(f"{match.group(1)}天")
                    if match.group(2): parts.append(f"{match.group(2)}小时")
                    if match.group(3): parts.append(f"{match.group(3)}分钟")
                    expiry_info = "".join(parts) if parts else "格式解析失败"
                logger.info(f"🕒 提取到剩余时间: {expiry_info}")
            except Exception as e: logger.warning(f"时间提取失败: {e}")

            # 3. 按钮点击
            target_btn = 'a[href*="tpi.li/FSfV"]'
            if sb.is_element_visible(target_btn):
                btn_class = sb.get_attribute(target_btn, "class")
                # 检查冷却状态
                if "pointer-events-none" in btn_class or "opacity-50" in btn_class:
                    status_report = f"按钮冷却中。目前剩余时间: {expiry_info}"
                    sb.save_screenshot("status.png")
                    send_tg_notification("尚在冷却中 🕒", status_report, "status.png")
                else:
                    sb.click(target_btn)
                    sb.sleep(5)
                    status_report = f"续期成功！操作前剩余: {expiry_info}"
                    sb.save_screenshot("success.png")
                    send_tg_notification("续期成功 ✅", status_report, "success.png")
            else:
                send_tg_notification("状态报告 📡", f"登录成功，剩余时间: {expiry_info}", None)

        except Exception as e:
            logger.error(f"💥 异常: {e}")
            sb.save_screenshot("error.png")
            send_tg_notification("流程异常 ❌", f"错误详情: `{str(e)}`", "error.png")
            raise e

if __name__ == "__main__":
    run_test()
