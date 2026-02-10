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
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(mail_address, app_password)
        mail.select("inbox")
        
        # 增加搜索范围，寻找未读或最新的 Pella 邮件
        for i in range(6): # 延长等待时间至 60 秒
            logger.info(f"🔍 正在扫描收件箱 (第 {i+1} 次尝试)...")
            status, messages = mail.search(None, '(FROM "Pella" UNSEEN)')
            if status == "OK" and messages[0]:
                break
            time.sleep(10)
        
        if not messages[0]:
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
    
    # 增加 slow_mode 模拟真人操作速度
    with SB(uc=True, xvfb=True) as sb:
        try:
            logger.info("第一步: 访问 Pella 登录页")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 10)
            sb.sleep(5)
            
            # 处理可能的 Cloudflare
            sb.uc_gui_click_captcha()

            logger.info(f"第二步: 输入邮箱 {email_addr}")
            # 使用你提供的 ID 选择器
            sb.wait_for_element_visible("#identifier-field", timeout=20)
            sb.type("#identifier-field", email_addr)
            sb.sleep(2)
            
            # 使用包含 Continue 的按钮点击
            sb.click('button:contains("Continue")') 
            
            logger.info("第三步: 等待邮件到达并抓取验证码...")
            sb.sleep(20) # 给邮件一点缓冲时间
            auth_code = get_pella_code(email_addr, app_pw)
            
            if not auth_code:
                sb.save_screenshot("no_code_error.png")
                raise Exception("验证码抓取失败，请检查邮件收件箱")

            logger.info(f"第四步: 填入验证码 {auth_code}")
            # 使用你提供的属性选择器定位验证码框
            otp_selector = 'input[data-input-otp="true"]'
            sb.wait_for_element_visible(otp_selector, timeout=10)
            
            # 有些 OTP 输入框需要模拟键盘逐个输入，我们先尝试直接 type
            sb.type(otp_selector, auth_code) 
            sb.sleep(10)
            
            logger.info("第五步: 检查登录结果")
            sb.save_screenshot("test_result.png")
            
            # 判断是否出现 nav 导航栏或 URL 变化来确定成功
            if not sb.is_element_present("#identifier-field"):
                logger.success("✅ Pella 登录流程模拟完成！")
            else:
                logger.error("❌ 仍停留在登录页，请检查截图")

        except Exception as e:
            logger.error(f"💥 测试中断: {e}")
            sb.save_screenshot("error_screenshot.png")
            raise e

if __name__ == "__main__":
    run_test()
