import os
import time
import imaplib
import email
import re
from seleniumbase import SB
from loguru import logger

def get_pella_code(mail_address, app_password):
    logger.info(f"📡 尝试连接 Gmail (IMAP)... 账户: {mail_address}")
    try:
        # 强制使用 Gmail IMAP 服务器
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(mail_address, app_password)
        mail.select("inbox")

        # 搜索未读邮件，增加重试机制
        for i in range(5):
            logger.info(f"🔍 正在扫描收件箱 (第 {i+1} 次尝试)...")
            status, messages = mail.search(None, '(FROM "Pella" UNSEEN)')
            if status == "OK" and messages[0]:
                break
            time.sleep(10)
        
        if not messages[0]:
            logger.warning("未找到未读邮件，尝试搜索最新的一封 Pella 邮件...")
            status, messages = mail.search(None, '(FROM "Pella")')

        if not messages[0]:
            return None

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
        return code.group() if code else None
    except Exception as e:
        logger.error(f"❌ 邮件读取失败: {e}")
        return None

def run_test():
    email_addr = os.environ.get("PELLA_EMAIL")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    
    with SB(uc=True, xvfb=True) as sb:
        try:
            logger.info("第一步: 访问 Pella 登录页")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 10)
            
            logger.info(f"第二步: 输入邮箱 {email_addr}")
            sb.wait_for_element_visible('input[type="email"]', timeout=20)
            sb.type('input[type="email"]', email_addr)
            sb.sleep(2)
            # 点击发送按钮
            sb.click('button:contains("Continue")') 
            
            logger.info("第三步: 等待邮件到达并抓取验证码...")
            sb.sleep(20)
            auth_code = get_pella_code(email_addr, app_pw)
            
            if not auth_code:
                raise Exception("验证码抓取失败，请检查 Gmail 是否开启 IMAP 权限或应用密码是否正确")

            logger.info(f"第四步: 填入验证码 {auth_code}")
            # Pella 登录框通常是 6 个 input 或者 1 个 input
            sb.type('input', auth_code) 
            sb.sleep(10)
            
            logger.info("第五步: 检查登录结果")
            sb.save_screenshot("test_result.png")
            if sb.is_element_visible('nav') or "login" not in sb.get_current_url():
                logger.success("✅ Pella 登录测试通过！")
            else:
                logger.error("❌ 登录似乎未完成，请检查截图")

        except Exception as e:
            logger.error(f"💥 测试中断: {e}")
            sb.save_screenshot("error_screenshot.png")
            raise e

if __name__ == "__main__":
    run_test()
