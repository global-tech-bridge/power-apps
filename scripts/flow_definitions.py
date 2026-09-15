#!/usr/bin/env python3
"""3つのクラウドフローの定義（Logic Apps ワークフロー定義）。

build-solution.py から読み込まれ、ソリューションの Workflows/*.json になる。
手順書 flows/*/README.md と expressions.md の内容を、そのまま機械可読にしたもの。
式の番号（E1 など）はコメントで対応付けてある。

コネクタの operationId は公式コネクタ リファレンスで確認済み。
  SharePoint            https://learn.microsoft.com/connectors/sharepointonline/
  Word Online (Business) https://learn.microsoft.com/connectors/wordonlinebusiness/
  Office 365 Outlook    https://learn.microsoft.com/connectors/office365/
"""

SP_API = "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"
WORD_API = "/providers/Microsoft.PowerApps/apis/shared_wordonlinebusiness"
MAIL_API = "/providers/Microsoft.PowerApps/apis/shared_office365"
ONEDRIVE_API = "/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness"

AUTH = "@parameters('$authentication')"

# トリガー入力の内部キー。Power Apps (V2) は宣言名ではなく型ごとの連番になる。
ITEM_ID = "@triggerBody()?['number']"
REQUEST_ID = "@triggerBody()?['text']"
SIGNATURE_IMAGE = "@triggerBody()?['text_1']"


# ---------------------------------------------------------------------------
# アクションを組み立てるヘルパー
# ---------------------------------------------------------------------------
def _conn(api, connection_name, operation_id, parameters, run_after=None, **extra):
    action = {
        "type": "OpenApiConnection",
        "inputs": {
            "host": {
                "connectionName": connection_name,
                "operationId": operation_id,
                "apiId": api,
            },
            "parameters": parameters,
            "authentication": AUTH,
        },
        "runAfter": run_after or {},
    }
    action.update(extra)
    return action


def sp(operation_id, parameters, run_after=None, **extra):
    return _conn(SP_API, "shared_sharepointonline", operation_id, parameters, run_after, **extra)


def word(operation_id, parameters, run_after=None, **extra):
    return _conn(WORD_API, "shared_wordonlinebusiness", operation_id, parameters, run_after, **extra)


def mail(operation_id, parameters, run_after=None, **extra):
    return _conn(MAIL_API, "shared_office365", operation_id, parameters, run_after, **extra)


def onedrive(operation_id, parameters, run_after=None, **extra):
    return _conn(
        ONEDRIVE_API, "shared_onedriveforbusiness", operation_id, parameters, run_after, **extra
    )


def delay(seconds, run_after=None):
    return {
        "type": "Wait",
        "inputs": {"interval": {"count": seconds, "unit": "Second"}},
        "runAfter": run_after or {},
    }


def compose(value, run_after=None):
    return {"type": "Compose", "inputs": value, "runAfter": run_after or {}}


def init_var(name, var_type, value, run_after=None):
    return {
        "type": "InitializeVariable",
        "inputs": {"variables": [{"name": name, "type": var_type, "value": value}]},
        "runAfter": run_after or {},
    }


def set_var(name, value, run_after=None):
    return {
        "type": "SetVariable",
        "inputs": {"name": name, "value": value},
        "runAfter": run_after or {},
    }


def scope(actions, run_after=None):
    return {"type": "Scope", "actions": actions, "runAfter": run_after or {}}


def if_(expression, then_actions, else_actions=None, run_after=None):
    action = {
        "type": "If",
        "expression": expression,
        "actions": then_actions,
        "runAfter": run_after or {},
    }
    if else_actions:
        action["else"] = {"actions": else_actions}
    return action


def respond(schema_properties, values, run_after=None):
    return {
        "type": "Response",
        "kind": "PowerApp",
        "inputs": {
            "statusCode": 200,
            "body": values,
            "schema": {"type": "object", "properties": schema_properties},
        },
        "runAfter": run_after or {},
    }


def after(*names, status=("Succeeded",)):
    return {n: list(status) for n in names}


FAILED = ("Failed", "Skipped", "TimedOut")


def powerapps_trigger(inputs, concurrency=None):
    """Power Apps (V2) トリガー。inputs は (内部キー, 表示名, 型) の並び。"""
    props = {}
    required = []
    for key, title, typ in inputs:
        hint = {"number": "NUMBER", "string": "TEXT"}[typ]
        props[key] = {
            "title": title,
            "type": typ,
            "x-ms-content-hint": hint,
            "x-ms-dynamically-added": True,
        }
        required.append(key)
    trigger = {
        "type": "Request",
        "kind": "PowerAppV2",
        "inputs": {"schema": {"type": "object", "properties": props, "required": required}},
    }
    if concurrency:
        # 文書番号の採番を直列化するための同時実行制御（要件定義 8章）
        trigger["runtimeConfiguration"] = {"concurrency": {"runs": concurrency}}
    return trigger


def _esc(expr):
    """HTML に埋め込む値をエスケープする式を返す。

    顧客名やコメントに < や & が入ると HTML が壊れ、変換後のPDFが崩れる。
    Power Automate に HTML エスケープ関数が無いため replace を3段重ねる。
    """
    return (
        f"replace(replace(replace(coalesce({expr},''),'&','&amp;'),'<','&lt;'),'>','&gt;')"
    )


def build_confirmation_html():
    """確認書のHTML。.doc として保存し OneDrive の変換で PDF にする。

    Word が読む HTML なので、A4縦・余白・日本語フォントを @page と CSS で指定する。
    レイアウトは元資料「分解・診断を伴う整備お見積り後のキャンセル料について.docx」
    （書簡形式＋確認欄）に合わせている。
    """
    case = "outputs('Get_case')?['body/{}']"

    def f(name):
        return "@{" + _esc(case.format(name)) + "}"

    # 確認文面は複数行テキスト。改行を <br> に変換する。
    consent = (
        "@{replace(replace("
        + _esc(case.format("ConsentTextSnapshot"))
        + ",decodeUriComponent('%0D'),''),decodeUriComponent('%0A'),'<br>')}"
    )
    serial = (
        "@{if(equals(outputs('Get_case')?['body/NoSerialNo'],true),'（機番なしの機体）',"
        + _esc(case.format("SerialNo"))
        + ")}"
    )
    comment = (
        "@{replace(replace("
        + _esc("coalesce(outputs('Get_case')?['body/Comment'],'（記載なし）')")
        + ",decodeUriComponent('%0D'),''),decodeUriComponent('%0A'),'<br>')}"
    )
    signed_at = (
        "@{formatDateTime(convertTimeZone(outputs('Get_case')?['body/SignedAt'],"
        "'UTC','Tokyo Standard Time'),'yyyy年MM月dd日 HH:mm')}"
    )
    signer = "@{" + _esc("coalesce(outputs('Get_case')?['body/SignerName'],'（記名なし）')") + "}"

    return (
        '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:w="urn:schemas-microsoft-com:office:word" '
        'xmlns="http://www.w3.org/TR/REC-html40"><head>'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
        "<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View>"
        "</w:WordDocument></xml><![endif]-->"
        "<style>"
        "@page{size:A4 portrait;margin:2.2cm 2.2cm 1.8cm 2.2cm;}"
        'body{font-family:"Yu Gothic","MS Gothic","Hiragino Kaku Gothic ProN",sans-serif;'
        "font-size:10.5pt;line-height:1.5;}"
        ".no{text-align:right;font-size:9pt;}"
        ".to{font-size:11pt;margin-bottom:10pt;}"
        ".from{text-align:right;font-size:10pt;line-height:1.3;}"
        ".title{text-align:center;font-size:13.5pt;font-weight:bold;margin:14pt 0;}"
        ".body{font-size:10pt;line-height:1.55;}"
        ".sec{font-size:11pt;font-weight:bold;margin:14pt 0 4pt 0;}"
        "table.k{border-collapse:collapse;width:100%;font-size:10pt;}"
        "table.k td{border:0.5pt solid #808080;padding:4pt 6pt;vertical-align:top;}"
        "table.k td.l{width:3.6cm;font-weight:bold;background:#f2f2f2;}"
        ".sign{height:3.4cm;}"
        ".sign img{height:3.2cm;}"
        ".foot{font-size:8pt;color:#605e5c;margin-top:10pt;}"
        "</style></head><body>"
        # 文書番号
        "<div class=\"no\">文書番号 <b>@{variables('varDocumentNo')}</b></div>"
        # 宛名
        f'<div class="to">{f("CustomerName")}　様</div>'
        # 差出人
        '<div class="from">ヤンマーアグリジャパン株式会社<br>'
        f'中部近畿支社　{f("BranchName")}　{f("BlockName")}　{f("SiteName")}<br>'
        f'担当　{f("OperatorName")}</div>'
        # 表題
        f'<div class="title">{f("ConsentTitle")}</div>'
        # 本文（署名時点のスナップショット）
        f'<div class="body">{consent}</div>'
        # 確認欄
        '<div class="sec">確認欄</div>'
        '<table class="k">'
        f'<tr><td class="l">型式</td><td>{f("Model")}</td></tr>'
        f'<tr><td class="l">機番</td><td>{serial}</td></tr>'
        f'<tr><td class="l">整備区分</td><td>{f("MaintenanceType/Value")}</td></tr>'
        f'<tr><td class="l">ご用命事項</td><td>{comment}</td></tr>'
        f'<tr><td class="l">お名前</td><td>{signer}</td></tr>'
        f'<tr><td class="l">日付</td><td>{signed_at}</td></tr>'
        '<tr><td class="l">ご署名</td><td class="sign">'
        "<img src=\"data:image/png;base64,@{variables('varSignatureBase64')}\">"
        "</td></tr>"
        "</table>"
        '<div class="foot">本書はヤンマーアグリジャパン株式会社 中部近畿支社の'
        "電子署名アプリで作成された電子文書です。この確認書のPDFが正本として保管されます。"
        "（確認文面 版 @{outputs('Get_case')?['body/ConsentVersion']}）</div>"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# Flow 1: YAJ-CancelFee-Submit
# ---------------------------------------------------------------------------
def submit_flow(cfg):
    site = cfg["sharePoint"]["siteUrl"]
    lists = cfg["sharePoint"]["lists"]
    libs = cfg["sharePoint"]["libraries"]
    tpl = cfg["wordTemplate"]
    cases = lists["signatureCases"]

    doc_no = "@{variables('varDocumentNo')}"

    # --- 採番（E3〜E8）-----------------------------------------------------
    numbering = {
        "Compose_DateKey": compose(
            "@formatDateTime(convertTimeZone(utcNow(),'UTC','Tokyo Standard Time'),'yyyyMMdd')"
        ),
        "Get_counter": sp(
            "GetItems",
            {
                "dataset": site,
                "table": lists["documentNumberCounter"],
                "$filter": "Title eq '@{outputs('Compose_DateKey')}'",
                "$top": 1,
            },
            after("Compose_DateKey"),
        ),
        "Counter_missing": if_(
            {"equals": ["@length(outputs('Get_counter')?['body/value'])", 0]},
            {
                "Create_counter": sp(
                    "PostItem",
                    {
                        "dataset": site,
                        "table": lists["documentNumberCounter"],
                        "item/Title": "@{outputs('Compose_DateKey')}",
                        "item/LastNumber": 0,
                    },
                )
            },
            run_after=after("Get_counter"),
        ),
        # カウンタを必ず存在させてから読み直す。分岐ごとに次の番号を組み立てると
        # 式が二重になり、片方を直し忘れる事故が起きるため。
        "Get_counter_again": sp(
            "GetItems",
            {
                "dataset": site,
                "table": lists["documentNumberCounter"],
                "$filter": "Title eq '@{outputs('Compose_DateKey')}'",
                "$top": 1,
            },
            after("Counter_missing"),
        ),
        "Compose_Next": compose(
            "@add(int(first(outputs('Get_counter_again')?['body/value'])?['LastNumber']),1)",
            after("Get_counter_again"),
        ),
        "Update_counter": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": lists["documentNumberCounter"],
                "id": "@first(outputs('Get_counter_again')?['body/value'])?['ID']",
                "item/Title": "@{outputs('Compose_DateKey')}",
                "item/LastNumber": "@outputs('Compose_Next')",
            },
            after("Compose_Next"),
        ),
        "Set_DocumentNo": set_var(
            "varDocumentNo",
            "@concat(outputs('Compose_DateKey'),'-',formatNumber(outputs('Compose_Next'),'000'))",
            after("Update_counter"),
        ),
    }

    # --- 署名画像 ----------------------------------------------------------
    signature_new = {
        "Set_SignatureBase64": set_var(
            "varSignatureBase64", f"@last(split({SIGNATURE_IMAGE[1:]},'base64,'))"
        ),
        "Create_signature_png": sp(
            "CreateFile",
            {
                "dataset": site,
                "folderPath": f"/{libs['signatureImages']}",
                "name": f"{doc_no}.png",
                "body": "@base64ToBinary(variables('varSignatureBase64'))",
            },
            after("Set_SignatureBase64"),
        ),
        "Set_SignatureUrl": set_var(
            "varSignatureUrl",
            "@outputs('Create_signature_png')?['body/{Link}']",
            after("Create_signature_png"),
        ),
    }
    signature_existing = {
        "Get_existing_png": sp(
            "GetFileContentByPath",
            {
                "dataset": site,
                "path": f"/{libs['signatureImages']}/{doc_no}.png",
                "inferContentType": True,
            },
        ),
        "Set_SignatureBase64_existing": set_var(
            "varSignatureBase64", "@base64(body('Get_existing_png'))", after("Get_existing_png")
        ),
        "Set_SignatureUrl_existing": set_var(
            "varSignatureUrl",
            "@coalesce(outputs('Get_case')?['body/SignatureImageUrl'],'')",
            after("Set_SignatureBase64_existing"),
        ),
    }

    # --- PDF 生成 ----------------------------------------------------------
    # Word Online (Business) は Premium コネクタ。
    # SharePoint コネクタには変換アクションが無いため、変換も Word Online の
    # GetFilePDF で行う（SharePoint 上のファイルを直接変換できる）。
    pdf_create = {
        "Populate_template": word(
            "CreateFileItem",
            {
                "source": tpl["source"],
                "drive": tpl["driveId"],
                "file": tpl["fileId"],
                "dynamicFileSchema/DocumentNo": doc_no,
                "dynamicFileSchema/CustomerName": "@{outputs('Get_case')?['body/CustomerName']}",
                "dynamicFileSchema/BranchName": "@{outputs('Get_case')?['body/BranchName']}",
                "dynamicFileSchema/BlockName": "@{outputs('Get_case')?['body/BlockName']}",
                "dynamicFileSchema/SiteName": "@{outputs('Get_case')?['body/SiteName']}",
                "dynamicFileSchema/OperatorName": "@{outputs('Get_case')?['body/OperatorName']}",
                "dynamicFileSchema/ConsentTitle": "@{outputs('Get_case')?['body/ConsentTitle']}",
                "dynamicFileSchema/ConsentText": "@{outputs('Get_case')?['body/ConsentTextSnapshot']}",
                "dynamicFileSchema/ConsentVersion": "@{outputs('Get_case')?['body/ConsentVersion']}",
                "dynamicFileSchema/Model": "@{outputs('Get_case')?['body/Model']}",
                "dynamicFileSchema/SerialNo":
                    "@{if(equals(outputs('Get_case')?['body/NoSerialNo'],true),"
                    "'（機番なしの機体）',coalesce(outputs('Get_case')?['body/SerialNo'],''))}",
                "dynamicFileSchema/MaintenanceType":
                    "@{outputs('Get_case')?['body/MaintenanceType/Value']}",
                "dynamicFileSchema/Comment":
                    "@{coalesce(outputs('Get_case')?['body/Comment'],'（記載なし）')}",
                "dynamicFileSchema/SignerName":
                    "@{coalesce(outputs('Get_case')?['body/SignerName'],'（記名なし）')}",
                "dynamicFileSchema/SignedAt":
                    "@{formatDateTime(convertTimeZone(outputs('Get_case')?['body/SignedAt'],"
                    "'UTC','Tokyo Standard Time'),'yyyy年MM月dd日 HH:mm')}",
                "dynamicFileSchema/SignatureImage": {
                    "$content-type": "image/png",
                    "$content": "@{variables('varSignatureBase64')}",
                },
            },
        ),
        "Create_temp_docx": sp(
            "CreateFile",
            {
                "dataset": site,
                "folderPath": f"/{libs['workTemp']}",
                "name": f"{doc_no}.docx",
                "body": "@body('Populate_template')",
            },
            after("Populate_template"),
        ),
        "Convert_to_pdf": word(
            "GetFilePDF",
            {
                "source": tpl["source"],
                "drive": "@{outputs('Create_temp_docx')?['body/{Path}']}",
                "file": "@{outputs('Create_temp_docx')?['body/{Identifier}']}",
            },
            after("Create_temp_docx"),
        ),
        "Create_pdf": sp(
            "CreateFile",
            {
                "dataset": site,
                "folderPath": f"/{libs['signatureDocs']}",
                "name": f"{doc_no}.pdf",
                "body": "@body('Convert_to_pdf')",
            },
            after("Convert_to_pdf"),
        ),
        "Set_PdfUrl": set_var(
            "varPdfUrl", "@outputs('Create_pdf')?['body/{Link}']", after("Create_pdf")
        ),
        "Update_case_pdf": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": cases,
                "id": ITEM_ID,
                "item/Status/Value": "Stored",
                "item/PdfUrl": "@{variables('varPdfUrl')}",
            },
            after("Set_PdfUrl"),
        ),
        # 変換が失敗しても中間ファイルを残さない
        "Delete_temp_docx": sp(
            "DeleteFile",
            {"dataset": site, "id": "@outputs('Create_temp_docx')?['body/{Identifier}']"},
            after("Update_case_pdf", status=("Succeeded", "Failed", "Skipped")),
        ),
    }
    pdf_reuse = {
        "Set_PdfUrl_existing": set_var(
            "varPdfUrl", "@coalesce(outputs('Get_case')?['body/PdfUrl'],'')"
        )
    }

    # --- PDF 生成（HTML→.doc 方式・標準コネクタのみ）------------------------
    # Word テンプレート方式は Word Online (Business)（Premium）を必要とし、
    # さらに MFA 条件付きアクセスが有効なテナントでは動かない既知の問題がある。
    # こちらは HTML を組み立てて .doc として保存し、OneDrive for Business
    # （標準コネクタ）の ConvertFileByPath で PDF に変換する。
    # 要件定義 10.1 で共有されていた「中間ファイルを .doc 形式にする案」そのもの。
    temp_folder = cfg["oneDrive"]["tempFolder"].rstrip("/")
    temp_path = f"{temp_folder}/{doc_no}.doc"

    pdf_create_html = {
        "Compose_Html": compose(build_confirmation_html(), run_after=None),
        # UTF-8 BOM を先頭に付ける。付けないと Word が文字コードを取り違えて
        # 日本語が文字化けする（要件定義 10.1 で共有されていた事象）。
        "Create_temp_doc": onedrive(
            "CreateFile",
            {
                "folderPath": temp_folder,
                "name": f"{doc_no}.doc",
                "body": "@{concat(decodeUriComponent('%EF%BB%BF'),outputs('Compose_Html'))}",
            },
            after("Compose_Html"),
        ),
        # コネクタの既知の問題: 作成直後に変換すると Bad gateway になることがある。
        # 公式リファレンスが「作成と変換の間の待ち時間を増やす」ことを推奨している。
        "Wait_for_file": delay(15, after("Create_temp_doc")),
        "Convert_to_pdf": onedrive(
            "ConvertFileByPath",
            {"path": temp_path, "type": "pdf"},
            after("Wait_for_file"),
        ),
        "Create_pdf": sp(
            "CreateFile",
            {
                "dataset": site,
                "folderPath": f"/{libs['signatureDocs']}",
                "name": f"{doc_no}.pdf",
                "body": "@body('Convert_to_pdf')",
            },
            after("Convert_to_pdf"),
        ),
        "Set_PdfUrl": set_var(
            "varPdfUrl", "@outputs('Create_pdf')?['body/{Link}']", after("Create_pdf")
        ),
        "Update_case_pdf": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": cases,
                "id": ITEM_ID,
                "item/Status/Value": "Stored",
                "item/PdfUrl": "@{variables('varPdfUrl')}",
            },
            after("Set_PdfUrl"),
        ),
        # 変換が失敗しても中間ファイルを残さない
        "Delete_temp_doc": onedrive(
            "DeleteFile",
            {"id": "@outputs('Create_temp_doc')?['body/Id']"},
            after("Update_case_pdf", status=("Succeeded", "Failed", "Skipped")),
        ),
    }

    # --- メール送信 --------------------------------------------------------
    body_html = (
        "<p>@{outputs('Get_case')?['body/CustomerName']} 様</p>"
        "<p>いつもお世話になっております。"
        "ヤンマーアグリジャパン @{outputs('Get_case')?['body/SiteName']} です。<br>"
        "このたびは、分解・診断を伴う整備お見積り後のキャンセル料についてご確認・"
        "ご署名をいただき、ありがとうございました。</p>"
        "<p>ご署名いただいた確認書をPDFで添付いたします。"
        "内容をご確認のうえ、控えとして保管をお願いいたします。</p>"
        "<table>"
        "<tr><td>文書番号</td><td>@{variables('varDocumentNo')}</td></tr>"
        "<tr><td>署名日時</td><td>@{formatDateTime(convertTimeZone("
        "outputs('Get_case')?['body/SignedAt'],'UTC','Tokyo Standard Time'),"
        "'yyyy年MM月dd日 HH:mm')}</td></tr>"
        "<tr><td>型式・機番</td><td>@{outputs('Get_case')?['body/Model']} / "
        "@{if(equals(outputs('Get_case')?['body/NoSerialNo'],true),'機番なし',"
        "coalesce(outputs('Get_case')?['body/SerialNo'],''))}</td></tr>"
        "<tr><td>整備区分</td><td>@{outputs('Get_case')?['body/MaintenanceType/Value']}</td></tr>"
        "<tr><td>担当者</td><td>@{outputs('Get_case')?['body/OperatorName']}</td></tr>"
        "</table>"
        "<p>本メールの内容にお心当たりがない場合、またご不明な点がある場合は、"
        "担当者までご連絡ください。</p>"
        f"<p>{cfg['mail']['companyName']}</p>"
    )
    recipients = (
        "@{outputs('Get_case')?['body/CustomerEmail']};"
        "@{outputs('Get_case')?['body/OperatorEmail']}"
    )
    send = {
        "Send_email": mail(
            "SendEmailV2",
            {
                "emailMessage/To": recipients,
                "emailMessage/Subject": f"{cfg['mail']['subjectPrefix']}（文書番号 {doc_no}）",
                "emailMessage/Body": body_html,
                "emailMessage/Attachments": [
                    {"Name": f"{doc_no}.pdf", "ContentBytes": "@body('Get_pdf_content')"}
                ],
                "emailMessage/Importance": "Normal",
            },
        ),
        "Update_case_sent": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": cases,
                "id": ITEM_ID,
                "item/Status/Value": "Sent",
                "item/SentAt": "@{utcNow()}",
                "item/ErrorCode": "",
                "item/ErrorMessage": "",
                "item/FlowRunId": "",
            },
            after("Send_email"),
        ),
        "Create_sendlog": sp(
            "PostItem",
            {
                "dataset": site,
                "table": lists["sendLog"],
                "item/Title": doc_no,
                "item/CaseId": ITEM_ID,
                "item/DocumentNo": doc_no,
                "item/SentTo": recipients,
                "item/SentBy": "@{outputs('Get_case')?['body/OperatorEmail']}",
                "item/SentAt": "@{utcNow()}",
                "item/Kind/Value": "Initial",
                "item/Result/Value": "Success",
            },
            after("Update_case_sent"),
        ),
    }

    # --- Try スコープ ------------------------------------------------------
    try_actions = {
        "Get_case": sp("GetItem", {"dataset": site, "table": cases, "id": ITEM_ID}),
        "Set_DocumentNo_existing": set_var(
            "varDocumentNo",
            "@coalesce(outputs('Get_case')?['body/DocumentNo'],'')",
            after("Get_case"),
        ),
        # 文書番号が既にあれば採番をまるごと飛ばす（再実行時の二重採番を防ぐ要点）
        "Need_number": if_(
            {"equals": ["@empty(variables('varDocumentNo'))", True]},
            numbering,
            run_after=after("Set_DocumentNo_existing"),
        ),
        "Update_case_number": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": cases,
                "id": ITEM_ID,
                "item/Title": doc_no,
                "item/DocumentNo": doc_no,
                "item/Status/Value": "Signed",
                "item/ClientRequestId": f"@{{{REQUEST_ID[1:]}}}",
                "item/PdfFileName": f"{doc_no}.pdf",
            },
            after("Need_number"),
        ),
        "Has_new_signature": if_(
            {"equals": [f"@empty({SIGNATURE_IMAGE[1:]})", False]},
            signature_new,
            signature_existing,
            run_after=after("Update_case_number"),
        ),
        "Update_case_signature": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": cases,
                "id": ITEM_ID,
                "item/SignatureImageUrl": "@{variables('varSignatureUrl')}",
            },
            after("Has_new_signature"),
        ),
        # PDFが既にあれば生成をまるごと飛ばす（再実行時の二重PDF生成を防ぐ要点）
        "Need_pdf": if_(
            {"equals": ["@empty(coalesce(outputs('Get_case')?['body/PdfUrl'],''))", True]},
            pdf_create_html if cfg["pdfMode"] == "html" else pdf_create,
            pdf_reuse,
            run_after=after("Update_case_signature"),
        ),
        # ファイル名を文書番号に固定しているため、初回でも再実行でも同じパスで取れる
        "Get_pdf_content": sp(
            "GetFileContentByPath",
            {
                "dataset": site,
                "path": f"/{libs['signatureDocs']}/{doc_no}.pdf",
                "inferContentType": True,
            },
            after("Need_pdf"),
        ),
        # 既に Sent のレコードへの再実行でメールを二重送信しないためのガード
        "Not_sent_yet": if_(
            {"equals": ["@outputs('Get_case')?['body/Status/Value']", "Sent"]},
            {},
            send,
            run_after=after("Get_pdf_content"),
        ),
    }

    # --- Catch スコープ ----------------------------------------------------
    failed_result = (
        "first(where(result('Try'),or(equals(item()?['status'],'Failed'),"
        "equals(item()?['status'],'TimedOut'))))"
    )
    error_code = (
        "@if(startsWith(outputs('Compose_FailedAction'),'Get_case'),'E-FLOW-010',"
        "if(or(startsWith(outputs('Compose_FailedAction'),'Get_counter'),"
        "startsWith(outputs('Compose_FailedAction'),'Create_counter'),"
        "startsWith(outputs('Compose_FailedAction'),'Update_counter'),"
        "startsWith(outputs('Compose_FailedAction'),'Update_case_number')),'E-FLOW-020',"
        "if(or(startsWith(outputs('Compose_FailedAction'),'Create_signature_png'),"
        "startsWith(outputs('Compose_FailedAction'),'Get_existing_png'),"
        "startsWith(outputs('Compose_FailedAction'),'Update_case_signature')),'E-FLOW-030',"
        "if(or(startsWith(outputs('Compose_FailedAction'),'Populate_template'),"
        "startsWith(outputs('Compose_FailedAction'),'Compose_Html'),"
        "startsWith(outputs('Compose_FailedAction'),'Create_temp_doc'),"
        "startsWith(outputs('Compose_FailedAction'),'Convert_to_pdf')),'E-FLOW-040',"
        "if(or(startsWith(outputs('Compose_FailedAction'),'Create_pdf'),"
        "startsWith(outputs('Compose_FailedAction'),'Update_case_pdf'),"
        "startsWith(outputs('Compose_FailedAction'),'Get_pdf_content')),'E-FLOW-050',"
        "if(or(startsWith(outputs('Compose_FailedAction'),'Send_email'),"
        "startsWith(outputs('Compose_FailedAction'),'Update_case_sent'),"
        "startsWith(outputs('Compose_FailedAction'),'Create_sendlog')),'E-FLOW-060',"
        "'E-FLOW-000')))))))"
    )
    user_message = (
        "@if(equals(outputs('Compose_ErrorCode'),'E-FLOW-020'),"
        "'文書番号の採番に失敗しました。時間をおいて、もう一度送信してください。',"
        "if(equals(outputs('Compose_ErrorCode'),'E-FLOW-030'),"
        "'署名画像の保存に失敗しました。もう一度送信してください。',"
        "if(equals(outputs('Compose_ErrorCode'),'E-FLOW-040'),"
        "'確認書PDFの作成に失敗しました。管理者に連絡してください。',"
        "if(equals(outputs('Compose_ErrorCode'),'E-FLOW-050'),"
        "'確認書PDFの保存に失敗しました。もう一度送信してください。',"
        "if(equals(outputs('Compose_ErrorCode'),'E-FLOW-060'),"
        "'PDFのメール送信に失敗しました。顧客メールアドレスを確認して、もう一度送信してください。',"
        "'処理中にエラーが発生しました。もう一度送信してください。')))))"
    )
    error_detail = (
        "@substring(string(coalesce(outputs('Compose_FailedResult')?['error'],'')),0,"
        "min(1800,length(string(coalesce(outputs('Compose_FailedResult')?['error'],'')))))"
    )

    catch_actions = {
        "Compose_FailedResult": compose("@" + failed_result),
        "Compose_FailedAction": compose(
            "@coalesce(outputs('Compose_FailedResult')?['name'],'Unknown')",
            after("Compose_FailedResult"),
        ),
        "Compose_ErrorDetail": compose(error_detail, after("Compose_FailedAction")),
        "Compose_ErrorCode": compose(error_code, after("Compose_ErrorDetail")),
        "Compose_UserMessage": compose(user_message, after("Compose_ErrorCode")),
        "Update_case_error": sp(
            "PatchItem",
            {
                "dataset": site,
                "table": cases,
                "id": ITEM_ID,
                "item/Status/Value": "Error",
                "item/ErrorCode": "@{outputs('Compose_ErrorCode')}",
                "item/ErrorMessage": "@{outputs('Compose_ErrorDetail')}",
                "item/FlowRunId": "@{workflow()['run']['name']}",
            },
            after("Compose_UserMessage"),
        ),
        "Respond_failure": respond(
            RESPONSE_SCHEMA,
            {
                "Success": False,
                "DocumentNo": "@{variables('varDocumentNo')}",
                "PdfUrl": "@{variables('varPdfUrl')}",
                "Status": "Error",
                "ErrorCode": "@{outputs('Compose_ErrorCode')}",
                "ErrorMessage": "@{outputs('Compose_UserMessage')}",
                "RunId": "@{workflow()['run']['name']}",
            },
            after("Update_case_error"),
        ),
    }

    return {
        "triggers": {
            "manual": powerapps_trigger(
                [
                    ("number", "ItemID", "number"),
                    ("text", "RequestId", "string"),
                    ("text_1", "SignatureImage", "string"),
                ],
                concurrency=1,
            )
        },
        "actions": {
            # 変数は Try の外で初期化する。Try が失敗しても Catch から読めるように。
            "Init_varDocumentNo": init_var("varDocumentNo", "string", ""),
            "Init_varPdfUrl": init_var("varPdfUrl", "string", "", after("Init_varDocumentNo")),
            "Init_varSignatureBase64": init_var(
                "varSignatureBase64", "string", "", after("Init_varPdfUrl")
            ),
            "Init_varSignatureUrl": init_var(
                "varSignatureUrl", "string", "", after("Init_varSignatureBase64")
            ),
            "Try": scope(try_actions, after("Init_varSignatureUrl")),
            "Catch": scope(catch_actions, after("Try", status=FAILED)),
            "Respond_success": respond(
                RESPONSE_SCHEMA,
                {
                    "Success": True,
                    "DocumentNo": "@{variables('varDocumentNo')}",
                    "PdfUrl": "@{variables('varPdfUrl')}",
                    "Status": "Sent",
                    "ErrorCode": "",
                    "ErrorMessage": "",
                    "RunId": "@{workflow()['run']['name']}",
                },
                after("Try"),
            ),
        },
    }


RESPONSE_SCHEMA = {
    "Success": {"title": "Success", "type": "boolean", "x-ms-dynamically-added": True},
    "DocumentNo": {"title": "DocumentNo", "type": "string", "x-ms-dynamically-added": True},
    "PdfUrl": {"title": "PdfUrl", "type": "string", "x-ms-dynamically-added": True},
    "Status": {"title": "Status", "type": "string", "x-ms-dynamically-added": True},
    "ErrorCode": {"title": "ErrorCode", "type": "string", "x-ms-dynamically-added": True},
    "ErrorMessage": {"title": "ErrorMessage", "type": "string", "x-ms-dynamically-added": True},
    "RunId": {"title": "RunId", "type": "string", "x-ms-dynamically-added": True},
}

SIMPLE_RESPONSE_SCHEMA = {
    "Success": {"title": "Success", "type": "boolean", "x-ms-dynamically-added": True},
    "ErrorCode": {"title": "ErrorCode", "type": "string", "x-ms-dynamically-added": True},
    "ErrorMessage": {"title": "ErrorMessage", "type": "string", "x-ms-dynamically-added": True},
    "RunId": {"title": "RunId", "type": "string", "x-ms-dynamically-added": True},
}


# ---------------------------------------------------------------------------
# Flow 2: YAJ-CancelFee-Resend（保存済みPDFの再送。PDFは作り直さない）
# ---------------------------------------------------------------------------
def resend_flow(cfg):
    site = cfg["sharePoint"]["siteUrl"]
    lists = cfg["sharePoint"]["lists"]
    libs = cfg["sharePoint"]["libraries"]
    cases = lists["signatureCases"]

    to_email = "@triggerBody()?['text']"
    case_doc_no = "@{outputs('Get_case')?['body/DocumentNo']}"

    try_actions = {
        "Get_case": sp("GetItem", {"dataset": site, "table": cases, "id": ITEM_ID}),
        "Pdf_exists": if_(
            {"equals": ["@empty(coalesce(outputs('Get_case')?['body/PdfUrl'],''))", False]},
            {
                "Get_pdf_content": sp(
                    "GetFileContentByPath",
                    {
                        "dataset": site,
                        "path": f"/{libs['signatureDocs']}/{case_doc_no}.pdf",
                        "inferContentType": True,
                    },
                ),
                "Send_email": mail(
                    "SendEmailV2",
                    {
                        "emailMessage/To": f"@{{{to_email[1:]}}}",
                        "emailMessage/Subject":
                            f"【再送】{cfg['mail']['subjectPrefix']}（文書番号 {case_doc_no}）",
                        "emailMessage/Body":
                            "<p>@{outputs('Get_case')?['body/CustomerName']} 様</p>"
                            "<p>本メールは、先にお送りした確認書の再送です。</p>"
                            "<p>ご署名いただいた確認書をPDFで添付いたします。"
                            "内容をご確認のうえ、控えとして保管をお願いいたします。</p>"
                            "<p>文書番号 " + case_doc_no + "</p>"
                            f"<p>{cfg['mail']['companyName']}</p>",
                        "emailMessage/Attachments": [
                            {
                                "Name": f"{case_doc_no}.pdf",
                                "ContentBytes": "@body('Get_pdf_content')",
                            }
                        ],
                    },
                    after("Get_pdf_content"),
                ),
                "Update_case": sp(
                    "PatchItem",
                    {
                        "dataset": site,
                        "table": cases,
                        "id": ITEM_ID,
                        "item/SentAt": "@{utcNow()}",
                        "item/ResendCount":
                            "@add(int(coalesce(outputs('Get_case')?['body/ResendCount'],0)),1)",
                    },
                    after("Send_email"),
                ),
                "Create_sendlog": sp(
                    "PostItem",
                    {
                        "dataset": site,
                        "table": lists["sendLog"],
                        "item/Title": case_doc_no,
                        "item/CaseId": ITEM_ID,
                        "item/DocumentNo": case_doc_no,
                        "item/SentTo": f"@{{{to_email[1:]}}}",
                        "item/SentAt": "@{utcNow()}",
                        "item/Kind/Value": "Resend",
                        "item/Result/Value": "Success",
                    },
                    after("Update_case"),
                ),
                "Create_auditlog": sp(
                    "PostItem",
                    {
                        "dataset": site,
                        "table": lists["auditLog"],
                        "item/Title": case_doc_no,
                        "item/Action/Value": "Resend",
                        "item/CaseId": ITEM_ID,
                        "item/DocumentNo": case_doc_no,
                        "item/PerformedAt": "@{utcNow()}",
                        "item/Reason": "PDF再送",
                        "item/Detail": f"送信先: @{{{to_email[1:]}}}",
                    },
                    after("Create_sendlog"),
                ),
            },
            {
                "Terminate_no_pdf": {
                    "type": "Terminate",
                    "inputs": {
                        "runStatus": "Failed",
                        "runError": {
                            "code": "E-RESEND-010",
                            "message": "保存済みPDFがありません",
                        },
                    },
                    "runAfter": {},
                }
            },
            run_after=after("Get_case"),
        ),
    }

    catch_actions = {
        "Compose_FailedResult": compose(
            "@first(where(result('Try'),or(equals(item()?['status'],'Failed'),"
            "equals(item()?['status'],'TimedOut'))))"
        ),
        "Create_sendlog_failure": sp(
            "PostItem",
            {
                "dataset": site,
                "table": lists["sendLog"],
                "item/Title": "RESEND-FAILED",
                "item/CaseId": ITEM_ID,
                "item/SentTo": f"@{{{to_email[1:]}}}",
                "item/SentAt": "@{utcNow()}",
                "item/Kind/Value": "Resend",
                "item/Result/Value": "Failure",
                "item/ErrorMessage":
                    "@{string(coalesce(outputs('Compose_FailedResult')?['error'],''))}",
            },
            after("Compose_FailedResult"),
        ),
        "Respond_failure": respond(
            SIMPLE_RESPONSE_SCHEMA,
            {
                "Success": False,
                "ErrorCode": "E-RESEND-020",
                "ErrorMessage": "再送に失敗しました。宛先を確認してください。",
                "RunId": "@{workflow()['run']['name']}",
            },
            after("Create_sendlog_failure"),
        ),
    }

    return {
        "triggers": {
            "manual": powerapps_trigger(
                [("number", "ItemID", "number"), ("text", "ToEmail", "string")]
            )
        },
        "actions": {
            "Try": scope(try_actions),
            "Catch": scope(catch_actions, after("Try", status=FAILED)),
            "Respond_success": respond(
                SIMPLE_RESPONSE_SCHEMA,
                {
                    "Success": True,
                    "ErrorCode": "",
                    "ErrorMessage": "",
                    "RunId": "@{workflow()['run']['name']}",
                },
                after("Try"),
            ),
        },
    }


# ---------------------------------------------------------------------------
# Flow 3: YAJ-CancelFee-Delete（管理者による誤登録データの削除）
# ---------------------------------------------------------------------------
def delete_flow(cfg):
    site = cfg["sharePoint"]["siteUrl"]
    lists = cfg["sharePoint"]["lists"]
    libs = cfg["sharePoint"]["libraries"]
    cases = lists["signatureCases"]

    reason = "@triggerBody()?['text']"
    doc_no = "@{outputs('Get_case')?['body/DocumentNo']}"

    try_actions = {
        "Get_case": sp("GetItem", {"dataset": site, "table": cases, "id": ITEM_ID}),
        # 削除の前に記録する。削除に失敗しても「削除しようとした事実」が残る。
        "Create_auditlog": sp(
            "PostItem",
            {
                "dataset": site,
                "table": lists["auditLog"],
                "item/Title":
                    "@{coalesce(outputs('Get_case')?['body/DocumentNo'],"
                    f"concat('ID-',string({ITEM_ID[1:]})))}}",
                "item/Action/Value": "Delete",
                "item/CaseId": ITEM_ID,
                "item/DocumentNo": doc_no,
                "item/PerformedAt": "@{utcNow()}",
                "item/Reason": f"@{{{reason[1:]}}}",
                "item/Detail":
                    "@{concat('顧客名: ',coalesce(outputs('Get_case')?['body/CustomerName'],''),"
                    "' / ステータス: ',coalesce(outputs('Get_case')?['body/Status/Value'],''),"
                    "' / 署名日時: ',coalesce(string(outputs('Get_case')?['body/SignedAt']),''),"
                    "' / PDF: ',coalesce(outputs('Get_case')?['body/PdfUrl'],'なし'))}",
            },
            after("Get_case"),
        ),
        # PDFや署名画像が未作成のドラフトも削除できるよう、失敗しても続行する
        "Delete_pdf": sp(
            "DeleteFile",
            {"dataset": site, "id": f"/{libs['signatureDocs']}/{doc_no}.pdf"},
            after("Create_auditlog"),
        ),
        "Delete_signature": sp(
            "DeleteFile",
            {"dataset": site, "id": f"/{libs['signatureImages']}/{doc_no}.png"},
            after("Delete_pdf", status=("Succeeded", "Failed")),
        ),
        "Delete_case": sp(
            "DeleteItem",
            {"dataset": site, "table": cases, "id": ITEM_ID},
            after("Delete_signature", status=("Succeeded", "Failed")),
        ),
    }

    catch_actions = {
        "Respond_failure": respond(
            SIMPLE_RESPONSE_SCHEMA,
            {
                "Success": False,
                "ErrorCode": "E-DELETE-010",
                "ErrorMessage": "削除に失敗しました。管理者に連絡してください。",
                "RunId": "@{workflow()['run']['name']}",
            },
        )
    }

    return {
        "triggers": {
            "manual": powerapps_trigger(
                [("number", "ItemID", "number"), ("text", "Reason", "string")]
            )
        },
        "actions": {
            "Try": scope(try_actions),
            "Catch": scope(catch_actions, after("Try", status=FAILED)),
            "Respond_success": respond(
                SIMPLE_RESPONSE_SCHEMA,
                {
                    "Success": True,
                    "ErrorCode": "",
                    "ErrorMessage": "",
                    "RunId": "@{workflow()['run']['name']}",
                },
                after("Try"),
            ),
        },
    }


FLOWS = [
    ("YAJ-CancelFee-Submit", submit_flow),
    ("YAJ-CancelFee-Resend", resend_flow),
    ("YAJ-CancelFee-Delete", delete_flow),
]
