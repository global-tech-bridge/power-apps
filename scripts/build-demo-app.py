#!/usr/bin/env python3
"""本番のキャンバスアプリ ソースから、接続なしで動くデモ版を生成する。

    python3 scripts/build-demo-app.py

目的
    SharePoint リスト・ドキュメント ライブラリ・Power Automate フローへの接続を
    一切せずに、**画面遷移だけ**をクライアントに確認してもらうための版。
    データはすべて App.OnStart で作るコレクション。アプリを閉じると消える。

方針
    画面・コントロール・レイアウトは本番と同一に保つ。差し替えるのは
      * App.OnStart        マスタとサンプル案件をベタ書きで作る
      * 保存処理           SharePoint への Patch → コレクションへの Collect/Patch
      * フロー呼び出し     採番・PDF・メール送信を、その場で完結する疑似処理に
    本番ソースを直したらこのスクリプトを実行し直せばデモ版も追随する。
"""
import csv
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "apps/yaj-cancelfee-signature/Src"
DST = ROOT / "apps/yaj-cancelfee-signature-demo/Src"
CONSENT = ROOT / "data/consent/ConsentText_v1.0.txt"
ORG_CSV = ROOT / "data/OrgMaster.csv"

# デモに載せる組織。全105拠点は要らないので、支社3種と各ブロックの先頭数件に絞る。
DEMO_ORG = {
    "営業部": {
        "福井ブロック": ["勝山", "大野", "鯖江", "福井"],
        "愛知ブロック": ["稲沢", "江南", "安城"],
        "兵庫ブロック": ["篠山", "三田", "三木"],
    },
    "販売部": {"販売部（ブロック未設定）": ["販売（福井）", "販売（愛知）", "販売（兵庫南）"]},
    "系統推進部": {"系統推進部（ブロック未設定）": ["系統中近Ｇ（福井）", "系統中近Ｇ（兵庫）"]},
}


def fx_string(text):
    """複数行テキストを Power Fx の文字列連結式にする。"""
    lines = text.rstrip("\n").split("\n")
    parts = []
    for i, line in enumerate(lines):
        safe = line.replace('"', '""')
        parts.append(f'"{safe}"')
        if i < len(lines) - 1:
            parts.append("Char(10)")
    # 読みやすいように4項目ずつ改行する
    out, buf = [], []
    for p in parts:
        buf.append(p)
        if len(buf) >= 6:
            out.append(" & ".join(buf))
            buf = []
    if buf:
        out.append(" & ".join(buf))
    joiner = "\n              & "
    return joiner.join(out)


def org_rows():
    """コード付きの組織行を作る。コードは本物のCSVから引く（無ければ合成）。"""
    real = {}
    with ORG_CSV.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            real[(r["BranchName"], r["BlockName"], r["SiteName"])] = (
                r["BlockCode"],
                r["SiteCode"],
            )
    rows = []
    for branch, blocks in DEMO_ORG.items():
        for block, sites in blocks.items():
            for site in sites:
                block_code, site_code = real.get(
                    (branch, block, site), ("DEMOBLK", "DEMOSITE")
                )
                rows.append((branch, block_code, block, site_code, site))
    return rows


def build_onstart():
    consent_title = CONSENT.read_text(encoding="utf-8").split("\n")[0].strip()
    consent_body = "\n".join(CONSENT.read_text(encoding="utf-8").split("\n")[2:]).strip()

    org = ",\n          ".join(
        '{BranchName: "%s", BlockCode: "%s", BlockName: "%s", SiteCode: "%s", SiteName: "%s"}'
        % r
        for r in org_rows()
    )

    # サンプル案件。ステータスを散らして、一覧の見え方を確認できるようにする。
    cases = [
        ("20260914-001", "田中農産 株式会社", "tanaka@example.co.jp", "0776-00-0001",
         "YT5113", "12345", False, "点検整備",
         "エンジンの掛かりが悪い。始動時に白煙が出る。",
         "営業部", "福井ブロック", "福井", "Sent", 2),
        ("20260915-001", "山本 太郎", "yamamoto@example.co.jp", "0587-00-0002",
         "EG438", "88213", False, "一般整備",
         "刈取部から異音。稲刈り前に見てほしい。",
         "営業部", "愛知ブロック", "稲沢", "Sent", 1),
        ("20260915-002", "佐藤牧場", "sato@example.co.jp", "",
         "YT225", "55012", False, "点検整備",
         "走行不良。ミッションの分解確認を希望。",
         "営業部", "兵庫ブロック", "三木", "Error", 1),
        ("20260916-001", "有限会社 鈴木ファーム", "suzuki@example.co.jp", "0776-00-0003",
         "RT250", "", True, "その他",
         "機番プレートが判読できない。",
         "販売部", "販売部（ブロック未設定）", "販売（福井）", "Sent", 0),
        ("", "中村 花子", "nakamura@example.co.jp", "",
         "YT347", "70118", False, "一般整備",
         "オイル漏れの疑い。訪問前に下書きだけ作成。",
         "営業部", "福井ブロック", "鯖江", "Draft", 0),
        ("", "大西 農園", "", "",
         "AG6114", "24007", False, "点検整備", "",
         "営業部", "兵庫ブロック", "篠山", "Draft", 0),
    ]

    def case_record(i, c):
        (doc, name, email, phone, model, serial, no_serial, mtype, comment,
         branch, block, site, status, days_ago) = c
        signed = status in ("Sent", "Error")
        return (
            "{\n"
            f"              ID: {i}, DocumentNo: \"{doc}\",\n"
            f"              CustomerName: \"{name}\", CustomerEmail: \"{email}\", "
            f"CustomerPhone: \"{phone}\",\n"
            f"              Model: \"{model}\", SerialNo: \"{serial}\", "
            f"NoSerialNo: {str(no_serial).lower()},\n"
            f"              MaintenanceType: {{Value: \"{mtype}\"}}, Comment: \"{comment}\",\n"
            f"              BranchName: \"{branch}\", BlockName: \"{block}\", "
            f"BlockCode: \"\", SiteName: \"{site}\", SiteCode: \"\",\n"
            f"              Status: {{Value: \"{status}\"}},\n"
            "              ConsentId: \"CANCELFEE-001\", ConsentTitle: varConsentTitle,\n"
            "              ConsentVersion: \"1.0\", ConsentTextSnapshot: varConsentBody,\n"
            f"              RegisteredAt: DateAdd(Now(), -{days_ago}, TimeUnit.Days),\n"
            f"              SignedAt: {f'DateAdd(Now(), -{days_ago}, TimeUnit.Days)' if signed else 'Blank()'},\n"
            "              SignerName: \"\",\n"
            "              OperatorEmail: varUserEmail, OperatorName: varUserName,\n"
            "              SignatureImageUrl: \"\", PdfUrl: "
            f"\"{'demo' if status == 'Sent' else ''}\", PdfFileName: \"{doc}.pdf\",\n"
            f"              SentAt: {f'DateAdd(Now(), -{days_ago}, TimeUnit.Days)' if status == 'Sent' else 'Blank()'},\n"
            "              ResendCount: 0, ClientRequestId: \"\",\n"
            f"              ErrorCode: \"{'E-FLOW-060' if status == 'Error' else ''}\",\n"
            f"              ErrorMessage: \"{'デモ用のエラー例です。' if status == 'Error' else ''}\",\n"
            "              FlowRunId: \"\"\n"
            "          }"
        )

    case_list = ",\n          ".join(case_record(i + 1, c) for i, c in enumerate(cases))

    return f"""=// ============================================================
      // デモ版 — 外部接続なし。データはすべてこの OnStart で作る。
      // SharePoint リスト／ドキュメント ライブラリ／Power Automate には
      // 一切つながない。アプリを閉じるとデータは消える。
      // 本番版: apps/yaj-cancelfee-signature/
      // ============================================================
      Set(varIsDemo, true);

      // ---- ログインユーザー -----------------------------------------------
      Set(varUserEmail, Lower(User().Email));
      Set(varUserName, User().FullName);
      // デモでは削除ボタンも見せたいので、常に管理者として扱う
      Set(varIsAdmin, true);
      ClearCollect(colAdmin, {{UserEmail: varUserEmail, IsActive: true}});

      // ---- 組織マスタ（本番は105拠点。デモは抜粋）-------------------------
      ClearCollect(colOrg,
          {org}
      );

      // ---- 確認文面（元資料 v1.0 をそのまま埋め込み）----------------------
      Set(varConsentTitle, "{consent_title}");
      Set(varConsentBody,
          {fx_string(consent_body)}
      );
      ClearCollect(colConsent,
          {{
              ConsentId: "CANCELFEE-001",
              Version: "1.0",
              DisplayTitle: varConsentTitle,
              Body: varConsentBody,
              EffectiveFrom: DateAdd(Now(), -30, TimeUnit.Days),
              EffectiveTo: Blank(),
              IsActive: true
          }}
      );
      Set(varConsent, First(colConsent));

      // ---- ステータス -----------------------------------------------------
      ClearCollect(colStatus,
          {{Code: "Draft",      Label: "作成中"}},
          {{Code: "Signed",     Label: "署名取得済み"}},
          {{Code: "PdfCreated", Label: "PDF生成済み"}},
          {{Code: "Stored",     Label: "SharePoint保存済み"}},
          {{Code: "Sent",       Label: "メール送信済み"}},
          {{Code: "Error",      Label: "エラー"}}
      );
      ClearCollect(colStatusOptions, ForAll(colStatus As s, {{Value: s.Label}}));

      // ---- 整備区分 -------------------------------------------------------
      ClearCollect(colMaintenanceType,
          {{Value: "点検整備"}},
          {{Value: "一般整備"}},
          {{Value: "その他"}}
      );

      // ---- サンプル案件 ---------------------------------------------------
      ClearCollect(colCases,
          {case_list}
      );
      Set(varNextCaseId, CountRows(colCases) + 1);

      // ---- 空レコードの雛形 ----------------------------------------------
      // 本番は Defaults(SignatureCases)。コレクションには Defaults が使えないため、
      // 同じ形の空レコードを1つ作って使い回す。
      Set(recBlankCase,
          Patch(First(colCases),
              {{
                  ID: 0, DocumentNo: "", CustomerName: "", CustomerEmail: "",
                  CustomerPhone: "", Model: "", SerialNo: "", NoSerialNo: false,
                  MaintenanceType: {{Value: "点検整備"}}, Comment: "",
                  BranchName: "", BlockName: "", BlockCode: "",
                  SiteName: "", SiteCode: "",
                  Status: {{Value: "Draft"}},
                  ConsentId: "", ConsentTitle: "", ConsentVersion: "",
                  ConsentTextSnapshot: "",
                  RegisteredAt: Blank(), SignedAt: Blank(), SignerName: "",
                  OperatorEmail: varUserEmail, OperatorName: varUserName,
                  SignatureImageUrl: "", PdfUrl: "", PdfFileName: "",
                  SentAt: Blank(), ResendCount: 0, ClientRequestId: "",
                  ErrorCode: "", ErrorMessage: "", FlowRunId: ""
              }}
          )
      );

      // ---- 組織の初期値 ---------------------------------------------------
      Set(varLastCase,
          First(Sort(Filter(colCases, OperatorEmail = varUserEmail), ID, SortOrder.Descending))
      );
      Set(varDefaultBranch, varLastCase.BranchName);
      Set(varDefaultBlock, varLastCase.BlockName);
      Set(varDefaultSite, varLastCase.SiteName);

      // ---- 編集中レコード -------------------------------------------------
      Set(varRecordId, 0);
      Set(varEdit, recBlankCase);
      Set(varRequestId, "");
      Set(varSignatureBase64, "");
      Set(varFilterStatusCode, "");

      // ---- デモ用: 次の送信でエラー画面を見せるかどうか --------------------
      Set(varDemoForceError, false)
"""


# ---------------------------------------------------------------------------
# 本番ソースに当てる差し替え
# ---------------------------------------------------------------------------
# デモ用の保存処理。SharePoint への Patch をコレクション操作に置き換える。
# Title 列と Operator（ユーザー列）は SharePoint 固有なので落としている。
DEMO_SAVE = """=// デモ: SharePoint ではなくコレクションへ保存する
              If(varRecordId = 0,
                  Set(varRecordId, varNextCaseId);
                  Set(varNextCaseId, varNextCaseId + 1);
                  Collect(colCases,
                      Patch(recBlankCase, {ID: varRecordId, RegisteredAt: Now()})
                  )
              );
              Patch(colCases, LookUp(colCases, ID = varRecordId),
                  {
                      CustomerName: Trim(txtCustomerName.Text),
                      CustomerEmail: Trim(txtCustomerEmail.Text),
                      CustomerPhone: Trim(txtCustomerPhone.Text),
                      Model: Trim(txtModel.Text),
                      SerialNo: If(chkNoSerial.Value, "", Trim(txtSerialNo.Text)),
                      NoSerialNo: chkNoSerial.Value,
                      MaintenanceType: {Value: ddMaintenanceType.Selected.Value},
                      Comment: txtComment.Text,
                      BranchName: ddBranch.Selected.Value,
                      BlockName: ddBlock.Selected.Value,
                      BlockCode: LookUp(colOrg,
                          BranchName = ddBranch.Selected.Value
                          && BlockName = ddBlock.Selected.Value,
                          BlockCode
                      ),
                      SiteName: ddSite.Selected.Value,
                      SiteCode: LookUp(colOrg,
                          BranchName = ddBranch.Selected.Value
                          && BlockName = ddBlock.Selected.Value
                          && SiteName = ddSite.Selected.Value,
                          SiteCode
                      ),
                      Status: {Value: "Draft"},
                      OperatorEmail: varUserEmail,
                      OperatorName: varUserName
                  }
              );
              Set(varEdit, LookUp(colCases, ID = varRecordId));"""

DEMO_SUBMIT = """=// デモ: フローを呼ばず、その場で採番して送信済みにする。
              // 本番では Power Automate が採番・PDF生成・SharePoint保存・メール送信を行う。
              If(IsBlank(varRequestId), Set(varRequestId, Text(GUID())));
              Set(varDemoDocNo,
                  Text(Now(), "yyyymmdd") & "-"
                  & Right("00" & Text(
                      CountRows(
                          Filter(colCases,
                              Text(RegisteredAt, "yyyymmdd") = Text(Now(), "yyyymmdd")
                              && !IsBlank(DocumentNo)
                          )
                      ) + 1
                  ), 3)
              );
              Patch(colCases, LookUp(colCases, ID = varRecordId),
                  {
                      DocumentNo: varDemoDocNo,
                      Status: {Value: If(varDemoForceError, "Error", "Sent")},
                      SignedAt: Now(),
                      SignerName: Trim(txtSignerName.Text),
                      ConsentId: varConsent.ConsentId,
                      ConsentTitle: varConsent.DisplayTitle,
                      ConsentVersion: varConsent.Version,
                      ConsentTextSnapshot: txtConsentBody.Text,
                      ClientRequestId: varRequestId,
                      SignatureImageUrl: penSignature.Image,
                      PdfUrl: If(varDemoForceError, "", "demo"),
                      PdfFileName: varDemoDocNo & ".pdf",
                      SentAt: If(varDemoForceError, Blank(), Now()),
                      ErrorCode: If(varDemoForceError, "E-FLOW-060", ""),
                      ErrorMessage: If(varDemoForceError, "デモ用に意図的に失敗させています。", "")
                  }
              );
              Set(varEdit, LookUp(colCases, ID = varRecordId));
              Set(varSubmitting, false);
              If(!varDemoForceError,
                  Set(varCompleted, LookUp(colCases, ID = varRecordId));
                  Navigate(CompleteScreen, ScreenTransition.Fade),
                  Set(varErrorCode, "E-FLOW-060");
                  Set(varErrorMessage,
                      "PDFのメール送信に失敗しました。顧客メールアドレスを確認して、もう一度送信してください。"
                  );
                  Set(varFlowRunId, "demo-00000000-0000-0000-0000-000000000000");
                  Navigate(ErrorScreen, ScreenTransition.Fade)
              )"""

DEMO_RETRY = """=// デモ: 再実行は必ず成功する
              Set(varRetrying, true);
              Patch(colCases, LookUp(colCases, ID = varRecordId),
                  {
                      Status: {Value: "Sent"},
                      PdfUrl: "demo",
                      SentAt: Now(),
                      ErrorCode: "",
                      ErrorMessage: ""
                  }
              );
              Set(varRetrying, false);
              Set(varCompleted, LookUp(colCases, ID = varRecordId));
              Navigate(CompleteScreen, ScreenTransition.Fade)"""

DEMO_RESEND = """=// デモ: 実際には送信しない
              Set(varShowResend, false);
              Patch(colCases, LookUp(colCases, ID = varSelected.ID),
                  {SentAt: Now(), ResendCount: varSelected.ResendCount + 1}
              );
              Set(varSelected, LookUp(colCases, ID = varSelected.ID));
              Notify(
                  "【デモ】署名済みPDFを再送しました。（" & Trim(txtResendTo.Text) & "）"
                      & " 本番では保存済みPDFが実際に添付されます。",
                  NotificationType.Success
              )"""

DEMO_DELETE = """=// デモ: コレクションから消すだけ。本番はPDFと署名画像も削除し監査ログに記録する。
              Set(varShowDelete, false);
              Remove(colCases, LookUp(colCases, ID = varSelected.ID));
              Notify(
                  "【デモ】削除しました。本番では署名画像とPDFも削除し、監査ログに記録します。",
                  NotificationType.Success
              );
              Navigate(ListScreen, ScreenTransition.UnCover)"""

DEMO_OPEN_PDF = """=Notify(
              "【デモ】PDFは生成されません。本番では署名済みPDFが開きます。",
              NotificationType.Information
            )"""

# デモ用のエラー確認チェックボックス（一覧画面の絞り込みパネルの空きに置く）
DEMO_ERROR_CHECKBOX = """      - chkDemoError:
          Control: Classic/CheckBox
          Properties:
            # デモ専用。次の送信を失敗させてエラー画面を見せるためのもの。
            Text: ="【デモ】次の送信をエラーにする"
            Default: =varDemoForceError
            OnCheck: =Set(varDemoForceError, true)
            OnUncheck: =Set(varDemoForceError, false)
            X: =300
            Y: =280
            Width: =290
            Height: =24
            Size: =10
            Color: =RGBA(196, 49, 75, 1)
"""


def replace_block(text, anchor, new_value, label):
    """`anchor` で始まるプロパティ値（次のプロパティ行まで）を丸ごと差し替える。"""
    i = text.find(anchor)
    if i < 0:
        sys.exit(f"差し替え対象が見つかりません: {label}")
    start = i + len(anchor)
    # 値の終わり = 同じかそれより浅いインデントで次のキーが始まる行
    indent = len(anchor) - len(anchor.lstrip(" ")) - 1
    rest = text[start:]
    m = re.search(rf"\n {{0,{indent}}}[A-Za-z#-]", rest)
    # ファイル末尾のプロパティには後続キーが無い
    tail = rest[m.start():] if m else "\n"
    body_indent = " " * (indent + 2)
    formatted = "\n".join(
        body_indent + line if line.strip() else line for line in new_value.split("\n")
    )
    return text[:start] + "\n" + formatted + tail


def main():
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    for path in sorted(SRC.glob("*.pa.yaml")):
        text = path.read_text(encoding="utf-8")
        name = path.name

        if name == "App.pa.yaml":
            text = replace_block(text, "    OnStart: |-", build_onstart(), "App.OnStart")
            text = text.replace(
                "# YAJ 整備キャンセル料 電子署名アプリ — アプリ定義",
                "# YAJ 整備キャンセル料 確認書アプリ — アプリ定義（デモ版・外部接続なし）",
            )

        elif name == "ListScreen.pa.yaml":
            text = text.replace("Filter(SignatureCases,", "Filter(colCases,")
            text = text.replace("Set(varEdit, Defaults(SignatureCases));", "Set(varEdit, recBlankCase);")
            # デモ用チェックボックスを chkMineOnly の直後に差し込む
            anchor = "      - btnClearFilter:"
            text = text.replace(anchor, DEMO_ERROR_CHECKBOX + anchor, 1)
            text = text.replace(
                'Text: ="整備キャンセル料 確認書"',
                'Text: ="整備キャンセル料 確認書（デモ）"',
            )

        elif name == "EditScreen.pa.yaml":
            # btnNext と btnSaveDraft は同じ保存内容。末尾の遷移だけ違う。
            text = replace_block(
                text, "            OnSelect: |-", DEMO_SAVE + """
              Navigate(ConsentScreen, ScreenTransition.Cover)""", "btnNext.OnSelect"
            )
            marker = "            Text: =\"ドラフト保存\""
            i = text.find(marker)
            head, tail = text[:i], text[i:]
            tail = replace_block(
                tail, "            OnSelect: |-", DEMO_SAVE + """
              Notify(
                  "ドラフトを保存しました。文書番号は確認・署名の送信時に採番されます。",
                  NotificationType.Success
              );
              Navigate(ListScreen, ScreenTransition.UnCover)""", "btnSaveDraft.OnSelect"
            )
            text = head + tail
            text = text.replace("Set(varEdit, Defaults(SignatureCases));", "Set(varEdit, recBlankCase);")

        elif name == "ConsentScreen.pa.yaml":
            text = replace_block(text, "            OnTimerEnd: |-", DEMO_SUBMIT, "tmrSubmit.OnTimerEnd")

        elif name == "CompleteScreen.pa.yaml":
            text = text.replace("Set(varEdit, Defaults(SignatureCases));", "Set(varEdit, recBlankCase);")

        elif name == "ErrorScreen.pa.yaml":
            text = replace_block(text, "            OnSelect: |-", DEMO_RETRY, "btnRetry.OnSelect")
            text = text.replace("LookUp(SignatureCases, ID = varRecordId)", "LookUp(colCases, ID = varRecordId)")

        elif name == "DetailScreen.pa.yaml":
            text = text.replace(
                "            OnSelect: =Launch(varSelected.PdfUrl)",
                "            OnSelect: |-\n              " + DEMO_OPEN_PDF.replace("\n", "\n  "),
            )
            for marker, block, label in (
                ('            Text: ="再送する"', DEMO_RESEND, "btnResendOk.OnSelect"),
                ('            Text: ="削除する"', DEMO_DELETE, "btnDeleteOk.OnSelect"),
            ):
                i = text.find(marker)
                if i < 0:
                    sys.exit(f"見つかりません: {label}")
                head, tail = text[:i], text[i:]
                text = head + replace_block(tail, "            OnSelect: |-", block, label)
            text = text.replace("LookUp(SignatureCases, ID = varSelected.ID)", "LookUp(colCases, ID = varSelected.ID)")
            text = text.replace('Text: ="確認書の詳細"', 'Text: ="確認書の詳細（デモ）"')

        # デモ版に残ってはいけない参照
        for forbidden in ("SignatureCases", "OrgMaster", "ConsentMaster", "AppAdmins",
                          "SendLog", "AuditLog", "DocumentNumberCounter",
                          "YAJ-CancelFee-", "SPListExpandedUser"):
            if forbidden in text:
                for line_no, line in enumerate(text.split("\n"), 1):
                    stripped = line.strip()
                    # YAML のコメント(#) と Power Fx のコメント(//) は対象外
                    if forbidden in line and not stripped.startswith(("#", "//")):
                        sys.exit(f"{name}:{line_no} に外部参照が残っています: {forbidden}\n  {line.strip()}")

        (DST / name).write_text(text, encoding="utf-8")
        print(f"  {name}")

    print(f"デモ版を生成しました: {DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
