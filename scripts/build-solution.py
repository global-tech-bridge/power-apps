#!/usr/bin/env python3
"""solution/config.json と flow_definitions.py から、pac でパックできる
ソリューション ソースツリーを生成する。

    python3 scripts/build-solution.py
    pac solution pack --zipfile solution/YAJCancelFeeSignature.zip \
        --folder solution/src --packagetype Unmanaged

生成物 solution/src/
    Other/Solution.xml         ソリューション マニフェスト（RootComponents を含む）
    Other/Customizations.xml   Workflows と connectionreferences の登録
    Other/Relationships.xml
    Workflows/<名前>-<GUID>.json  各クラウドフローの定義

GUID は名前から決定的に生成する（uuid5）。再生成しても同じ値になるので、
差分が出るのは実際に定義を変えたときだけになる。
"""
import json
import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
import flow_definitions as fd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "solution/config.json").read_text(encoding="utf-8"))
SRC = ROOT / "solution/src"

# 決定的な GUID を作るための名前空間（このプロジェクト固有の固定値）
NS = uuid.UUID("6f2b1c94-3a7d-5e11-9c4a-8d0e5b2f7a63")

# ワークフローのカテゴリ 5 = モダン フロー（クラウド フロー）
WORKFLOW_CATEGORY = 5
# ソリューション コンポーネント種別
COMPONENT_WORKFLOW = 29
COMPONENT_CONNECTION_REFERENCE = 10088

SCHEMA = (
    "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/"
    "2016-06-01/workflowdefinition.json#"
)

# 使うコネクタと、接続参照の論理名に使う接尾辞
CONNECTORS = {
    "shared_sharepointonline": "sharepointonline",
    "shared_wordonlinebusiness": "wordonlinebusiness",
    "shared_office365": "office365",
    "shared_onedriveforbusiness": "onedriveforbusiness",
}


def guid(*parts):
    return str(uuid.uuid5(NS, "|".join(parts)))


def connection_reference_name(connector):
    """接続参照の論理名。prefix_<コネクタ>_<短いハッシュ> 形式にする。"""
    prefix = CFG["solution"]["publisherPrefix"]
    short = guid("connref", connector).replace("-", "")[:10]
    return f"{prefix}_{CONNECTORS[connector]}_{short}"


def used_connectors(definition):
    """フロー定義を走査して、実際に使っているコネクタを拾う。"""
    found = set()

    def walk(node):
        if isinstance(node, dict):
            host = node.get("host")
            if isinstance(host, dict) and "connectionName" in host:
                found.add(host["connectionName"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(definition)
    return sorted(found)


def build_workflow_json(name, definition):
    connectors = used_connectors(definition)
    refs = {
        c: {
            "runtimeSource": "embedded",
            "connection": {"connectionReferenceLogicalName": connection_reference_name(c)},
            "api": {"name": c},
        }
        for c in connectors
    }
    return {
        "properties": {
            "connectionReferences": refs,
            "definition": {
                "$schema": SCHEMA,
                "contentVersion": "1.0.0.0",
                "parameters": {
                    "$connections": {"defaultValue": {}, "type": "Object"},
                    "$authentication": {"defaultValue": {}, "type": "SecureObject"},
                },
                "triggers": definition["triggers"],
                "actions": definition["actions"],
            },
        },
        "schemaVersion": "1.0.0.0",
    }


def workflow_xml(name, workflow_id, json_file):
    """Workflows/<名前>-<GUID>.json.data.xml の中身。

    SolutionPackager の正規形式（pac solution unpack の出力と同じ）:
      * Customizations.xml の <Workflows> は **空要素**
      * メタデータは Workflows/<名前>-<GUID>.json.data.xml に置く
      * 定義は     Workflows/<名前>-<GUID>.json
    pack 時に .json.data.xml が customizations.xml へマージされる。
    子要素を Customizations.xml に直接書くと「unexpected children」警告が出る。
    """
    return f"""<Workflow WorkflowId="{{{workflow_id}}}" Name="{escape(name)}">
  <JsonFileName>/Workflows/{escape(json_file)}</JsonFileName>
  <Type>1</Type>
  <Subprocess>0</Subprocess>
  <Category>{WORKFLOW_CATEGORY}</Category>
  <Mode>0</Mode>
  <Scope>4</Scope>
  <OnDemand>0</OnDemand>
  <TriggerOnCreate>0</TriggerOnCreate>
  <TriggerOnDelete>0</TriggerOnDelete>
  <AsyncAutodelete>0</AsyncAutodelete>
  <SyncWorkflowLogOnFailure>0</SyncWorkflowLogOnFailure>
  <StateCode>1</StateCode>
  <StatusCode>2</StatusCode>
  <RunAs>1</RunAs>
  <IsTransacted>1</IsTransacted>
  <IntroducedVersion>1.0.0.0</IntroducedVersion>
  <IsCustomizable>1</IsCustomizable>
  <BusinessProcessType>0</BusinessProcessType>
  <IsCustomProcessingStepAllowedForOtherPublishers>1</IsCustomProcessingStepAllowedForOtherPublishers>
  <PrimaryEntity>none</PrimaryEntity>
  <LocalizedNames>
    <LocalizedName languagecode="1041" description="{escape(name)}" />
  </LocalizedNames>
</Workflow>
"""


def connection_reference_xml(connector):
    logical = connection_reference_name(connector)
    return f"""    <connectionreference connectionreferencelogicalname="{logical}">
      <connectionreferencedisplayname>{escape(logical)}</connectionreferencedisplayname>
      <connectionreferencelogicalname>{logical}</connectionreferencelogicalname>
      <connectorid>/providers/Microsoft.PowerApps/apis/{connector}</connectorid>
      <iscustomizable>1</iscustomizable>
      <promptingbehavior>0</promptingbehavior>
      <statecode>0</statecode>
      <statuscode>1</statuscode>
    </connectionreference>"""


def main():
    sol = CFG["solution"]
    SRC.mkdir(parents=True, exist_ok=True)
    (SRC / "Other").mkdir(exist_ok=True)
    (SRC / "Workflows").mkdir(exist_ok=True)

    # 既存の Workflows を消してから書き直す（名前を変えたときのゴミを残さない）
    for old in list((SRC / "Workflows").glob("*.json")) + list(
        (SRC / "Workflows").glob("*.xml")
    ):
        old.unlink()

    workflows = []
    all_connectors = set()

    for name, builder in fd.FLOWS:
        definition = builder(CFG)
        wf_id = guid("workflow", name)
        json_file = f"{name.replace('-', '')}-{wf_id.upper()}.json"
        payload = build_workflow_json(name, definition)
        (SRC / "Workflows" / json_file).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (SRC / "Workflows" / (json_file + ".data.xml")).write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n' + workflow_xml(name, wf_id, json_file),
            encoding="utf-8",
        )
        workflows.append((name, wf_id, json_file))
        all_connectors |= set(used_connectors(definition))

    connectors = sorted(all_connectors)

    # ---- Customizations.xml ----
    customizations = f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Entities />
  <Roles />
  <Workflows />
  <FieldSecurityProfiles />
  <Templates />
  <EntityMaps />
  <EntityRelationships />
  <OrganizationSettings />
  <optionsets />
  <CustomControls />
  <SolutionPluginAssemblies />
  <EntityDataProviders />
  <connectionreferences>
{chr(10).join(connection_reference_xml(c) for c in connectors)}
  </connectionreferences>
  <Languages>
    <Language>1041</Language>
  </Languages>
</ImportExportXml>
"""
    (SRC / "Other/Customizations.xml").write_text(customizations, encoding="utf-8")

    # ---- Solution.xml ----
    root_components = "\n".join(
        f'      <RootComponent type="{COMPONENT_WORKFLOW}" id="{{{i}}}" behavior="0" />'
        for _, i, _ in workflows
    )
    root_components += "\n" + "\n".join(
        f'      <RootComponent type="{COMPONENT_CONNECTION_REFERENCE}" '
        f'schemaName="{connection_reference_name(c)}" behavior="0" />'
        for c in connectors
    )

    solution = f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml version="9.2.24025.180" SolutionPackageVersion="9.2" languagecode="1041" generatedBy="CrmLive" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <SolutionManifest>
    <UniqueName>{escape(sol['uniqueName'])}</UniqueName>
    <LocalizedNames>
      <LocalizedName description="{escape(sol['displayName'])}" languagecode="1041" />
    </LocalizedNames>
    <Descriptions>
      <Description description="YAJ 整備キャンセル料 確認書アプリのクラウドフロー" languagecode="1041" />
    </Descriptions>
    <Version>{sol['version']}</Version>
    <Managed>0</Managed>
    <Publisher>
      <UniqueName>{escape(sol['publisherUniqueName'])}</UniqueName>
      <LocalizedNames>
        <LocalizedName description="{escape(sol['publisherDisplayName'])}" languagecode="1041" />
      </LocalizedNames>
      <Descriptions>
        <Description description="{escape(sol['publisherDisplayName'])}" languagecode="1041" />
      </Descriptions>
      <EMailAddress xsi:nil="true"></EMailAddress>
      <SupportingWebsiteUrl xsi:nil="true"></SupportingWebsiteUrl>
      <CustomizationPrefix>{escape(sol['publisherPrefix'])}</CustomizationPrefix>
      <CustomizationOptionValuePrefix>{sol['optionValuePrefix']}</CustomizationOptionValuePrefix>
      <Addresses>
        <Address>
          <AddressNumber>1</AddressNumber>
          <AddressTypeCode>1</AddressTypeCode>
          <City xsi:nil="true"></City>
          <County xsi:nil="true"></County>
          <Country xsi:nil="true"></Country>
          <Fax xsi:nil="true"></Fax>
          <FreightTermsCode xsi:nil="true"></FreightTermsCode>
          <ImportSequenceNumber xsi:nil="true"></ImportSequenceNumber>
          <Latitude xsi:nil="true"></Latitude>
          <Line1 xsi:nil="true"></Line1>
          <Line2 xsi:nil="true"></Line2>
          <Line3 xsi:nil="true"></Line3>
          <Longitude xsi:nil="true"></Longitude>
          <Name xsi:nil="true"></Name>
          <PostalCode xsi:nil="true"></PostalCode>
          <PostOfficeBox xsi:nil="true"></PostOfficeBox>
          <PrimaryContactName xsi:nil="true"></PrimaryContactName>
          <ShippingMethodCode>1</ShippingMethodCode>
          <StateOrProvince xsi:nil="true"></StateOrProvince>
          <Telephone1 xsi:nil="true"></Telephone1>
          <Telephone2 xsi:nil="true"></Telephone2>
          <Telephone3 xsi:nil="true"></Telephone3>
          <TimeZoneRuleVersionNumber xsi:nil="true"></TimeZoneRuleVersionNumber>
          <UPSZone xsi:nil="true"></UPSZone>
          <UTCOffset xsi:nil="true"></UTCOffset>
          <UTCConversionTimeZoneCode xsi:nil="true"></UTCConversionTimeZoneCode>
        </Address>
        <Address>
          <AddressNumber>2</AddressNumber>
          <AddressTypeCode>1</AddressTypeCode>
          <City xsi:nil="true"></City>
          <County xsi:nil="true"></County>
          <Country xsi:nil="true"></Country>
          <Fax xsi:nil="true"></Fax>
          <FreightTermsCode xsi:nil="true"></FreightTermsCode>
          <ImportSequenceNumber xsi:nil="true"></ImportSequenceNumber>
          <Latitude xsi:nil="true"></Latitude>
          <Line1 xsi:nil="true"></Line1>
          <Line2 xsi:nil="true"></Line2>
          <Line3 xsi:nil="true"></Line3>
          <Longitude xsi:nil="true"></Longitude>
          <Name xsi:nil="true"></Name>
          <PostalCode xsi:nil="true"></PostalCode>
          <PostOfficeBox xsi:nil="true"></PostOfficeBox>
          <PrimaryContactName xsi:nil="true"></PrimaryContactName>
          <ShippingMethodCode>1</ShippingMethodCode>
          <StateOrProvince xsi:nil="true"></StateOrProvince>
          <Telephone1 xsi:nil="true"></Telephone1>
          <Telephone2 xsi:nil="true"></Telephone2>
          <Telephone3 xsi:nil="true"></Telephone3>
          <TimeZoneRuleVersionNumber xsi:nil="true"></TimeZoneRuleVersionNumber>
          <UPSZone xsi:nil="true"></UPSZone>
          <UTCOffset xsi:nil="true"></UTCOffset>
          <UTCConversionTimeZoneCode xsi:nil="true"></UTCConversionTimeZoneCode>
        </Address>
      </Addresses>
    </Publisher>
    <RootComponents>
{root_components}
    </RootComponents>
    <MissingDependencies />
  </SolutionManifest>
</ImportExportXml>
"""
    (SRC / "Other/Solution.xml").write_text(solution, encoding="utf-8")

    (SRC / "Other/Relationships.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<EntityRelationships xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" />\n',
        encoding="utf-8",
    )

    mode = CFG.get("pdfMode", "html")
    mode_label = {
        "html": "HTML→.doc（標準コネクタのみ。追加ライセンス不要）",
        "wordTemplate": "Word テンプレート（Word Online (Business) = Premium が必要）",
    }[mode]
    print(f"solution/src/ を生成しました（{sol['uniqueName']} v{sol['version']}）")
    print(f"  PDF生成方式: {mode_label}")
    for name, wf_id, json_file in workflows:
        print(f"  Workflows/{json_file}")
        print(f"      {name}  id={wf_id}")
    print(f"  接続参照 {len(connectors)} 件")
    for c in connectors:
        print(f"      {connection_reference_name(c)}  <- {c}")

    site = CFG["sharePoint"]["siteUrl"]
    if "CONTOSO" in site:
        print("\n⚠ solution/config.json の siteUrl が既定値のままです。実環境のURLに変更してください。")
    if mode == "wordTemplate" and "PLACEHOLDER" in json.dumps(CFG["wordTemplate"]):
        print("⚠ wordTemplate の source / driveId / fileId が未解決です。")
        print("  scripts/resolve-template-ids.sh で取得するか、インポート後に")
        print("  Populate_template アクションでテンプレートを選び直してください。")
    if mode == "html":
        print(f"  中間 .doc の置き場: {CFG['oneDrive']['tempFolder']}"
              "（接続アカウントの OneDrive）")


if __name__ == "__main__":
    main()
