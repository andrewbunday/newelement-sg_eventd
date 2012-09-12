import os
import logging
import smtplib
import string
from email.utils import formatdate
import email.mime.multipart
import email.mime.text

SMTP_HOST = "email.yourdomain.com"
FROM_ADDR = "spamalot@yourdomain.com"
REPLY_TO_ADDRESS = "no-reply@yourdomain.com"
LOGIN = "login@yourdomain.com"
PASSWD = "ilikechocolatemilk"

EMAIL_FORMAT_STRING = """{user} created {code} on {shot}

Notes: {notes}
Frames: {frames}

Shot: {shot}

To learn how to setup filters on your gmail account visit: http://support.google.com/mail/bin/answer.py?hl=en&answer=6579
"""

HTML_FORMAT_STRING = """\
<html>
    <head></head>
    <body>
        {user} created <a href='{elink}'>{code}</a> on <a href='{slink}'>{shot}</a>
        <p>
        Notes: {notes}
        <p>
        Frames: <a href="rvlink://baked/{flink}">{frames}</a>
        <p>
        <p>
        <p>
        To learn how to setup filters on your gmail account visit: http://support.google.com/mail/bin/answer.py?hl=en&answer=6579
    </body>
</html>
"""

def registerCallbacks(reg):

    matchEvents = {"Shotgun_Element_New": ['*'],}
    reg.registerCallback('Spamalot', '$YOUR_SCRIPT_KEY$', processNewElement, matchEvents, None)
    reg.logger.setLevel(logging.INFO)

def processNewElement(sg, logger, event, args):

    logger.info("%s" % str(event))

    if not event.get("entity"):
        logger.info("event contains no entity link. skipping emails")
        return

    element = sg.find_one("Element", filters=[["id","is",event['entity']['id']]],
                          fields=["id","shots","updated_by","code","sg_path_to_frames","description","project"])

    users = set()
    users.add(event["user"]["name"])
    users.add(element["updated_by"]["name"])

    fields = ["id", "code"]
    for shot_entity in element["shots"]:
        shot = sg.find_one("Shot", filters=[["id","is",shot_entity["id"]]], fields=fields)

        filters = [["event_type", "is", "Shotgun_Shot_Change"], ["entity", "is", shot]]
        for old_event in sg.find("EventLogEntry", filters=filters, fields=["id", "entity", "user"]):
            users.add(old_event["user"]["name"])

        for version in sg.find("Version", filters=[["entity.Shot.code", "is", shot["code"]]], fields=["id", "user"]):
            users.add(version["user"]["name"])

        for task in sg.find("Task", filters=[["entity.Shot.code", "is", shot["code"]]], fields=["id", "task_assignees"]):
            for user in task["task_assignees"]:
                users.add(user["name"])

    email_list = set()
    for user in sg.find("HumanUser", filters=[["sg_status_list","is", "act"]], fields=["login", "email", "name", "permission_rule_set"]):
        if (user["name"] in users) or (user["permission_rule_set"]["name"] == "DataOp"):
            email_list.add(user["email"])

    emailShot(element, list(email_list))
    logger.info("emails sent to %s" % list(email_list))

def emailShot(element, toaddrs=[]):

    def getSubject(element):
        code = element["code"]
        user = element["updated_by"]["name"]
        project = element["project"]["name"]
        shot = element["shots"][0]["name"]
        return "[New Element] Shot {shot} Element {code} ({project})".format(shot=shot, code=code, project=project)

    def getTextBody(element):
        """Return a Plain Text encoded representation of the email."""
        return EMAIL_FORMAT_STRING.format(user=element["updated_by"]["name"],
                                          shot=element["shots"][0]["name"],
                                          notes=element["description"],
                                          code=element["code"],
                                          frames=os.path.basename(element["sg_path_to_frames"]),
                                         )

    def getHTMLBody(element):
        """Return an HTML encoded representation of the email."""

        rvlink = "-l -play %s" % element["sg_path_to_frames"]

        return HTML_FORMAT_STRING.format(elink="http://EXAMPLE.shotgunstudio.com/detail/Element/%d" % element["id"],
           slink="http://EXAMPLE.shotgunstudio.com/detail/Shot/%d" % element["shots"][0]["id"],
           user=element["updated_by"]["name"],
           shot=element["shots"][0]["name"],
           notes=element["description"],
           code=element["code"],
           frames=element["sg_path_to_frames"],
           flink=rvlink.encode('hex'))

    try:
        port = smtplib.SMTP_PORT
        smtp = smtplib.SMTP(SMTP_HOST, port)

        msg = email.mime.multipart.MIMEMultipart('alternative')
        msg["To"] = string.join(toaddrs, ",")
        msg["From"] = FROM_ADDR
        msg["Subject"] = getSubject(element)
        msg.add_header("Reply-To", REPLY_TO_ADDRESS)

        text = getTextBody(element)
        html = getHTMLBody(element)

        msg.attach(email.mime.text.MIMEText(text, "plain"))
        msg.attach(email.mime.text.MIMEText(html, "html"))

        # TLS login data, required for webmail SMTP servers. ie gmail/mediatemple
        if LOGIN:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(LOGIN, PASSWD)
        result = smtp.sendmail(FROM_ADDR, toaddrs, msg.as_string())
        smtp.quit()

    except (KeyboardInterrupt, SystemExit) as e:
        print e
        raise
    except Exception as e:
        print(e)
