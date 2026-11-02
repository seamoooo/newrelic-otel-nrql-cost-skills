---
name: newrelic-otel-query-cost
description: Review and optimize NRQL cost for OpenTelemetry SDK, Collector and NRDOT data sent to New Relic over OTLP. Span・Metric・Logの対象と集計を維持する。APMエージェントによるOTel API取り込みは対象外。
---

# New Relic OpenTelemetry NRQL Cost Optimization

必要な答えを維持しながら、NRQLの対象範囲・処理・実行回数・応答量を見直す。ユーザーの言語に合わせて答える。料金やCCUは、対応する計測値と契約条件から評価する。

## 目的と前提を確認する

調査目的、アカウント・サービス、必要期間、用途（単発／反復／アラート）を提示内容から把握する。対象アカウントが不明ならユーザーに確認し、実行前の静的評価を進める。

例示クエリのイベント型・属性名・値は対象環境では未検証として扱う。`dimension_productCapability`、`service.name`、`level`等は、既存のスキーマ情報または許可された最小限の確認で実名・型・値を照合する。

対象はOpenTelemetry SDK・Collector・NRDOTからNew RelicへのOTLP送信。個別transaction/transaction traceはSpanから取得し、Transaction・TransactionErrorの存在を仮定しない。HTTP/RPCは対象サービスのserver Span、非Web処理は計装に合う処理境界を選ぶ。trace全体のrootだけへ限定しない。

全体の件数・応答時間・エラー率は適合する既存Metricを優先する。サンプリング済みSpanを全リクエストと扱わず、単位とエラー定義を照合する。New RelicエージェントがOTel APIを取り込む構成は対象外。混在環境ではOTLP由来のentity・収集元を限定する。

必要な内容だけ参照する。

- OTLPのデータ選択・単位・エラー定義と例：[opentelemetry.md](references/opentelemetry.md)
- 型・関連ID・欠測・Kubernetes等：[opentelemetry-data-model.md](references/opentelemetry-data-model.md)
- DB360・receiver・Prometheusの集計条件：[opentelemetry-integrations.md](references/opentelemetry-integrations.md)
- 改善例・検索やカーディナリティ：[query-patterns.md](references/query-patterns.md)
- 計測と結果の比較：[measurement.md](references/measurement.md)
- サイト性能・反復調査の運用：[operations.md](references/operations.md)
- NerdGraph経由のNRQL実行計画：[nerdgraph.md](references/nerdgraph.md)

## 実行経路を確認する

ハーネスが現在のセッションに公開している、登録済みのNew Relic MCPツールだけを使う。名前・引数・戻り値・読み取り権限を確認し、ハーネスの承認手順に従う。

**資格情報を取得するために設定ファイル・環境変数・キー保管場所を探索したり、取得した資格情報で独自HTTPクライアント等から直接接続したりして、ツールの権限管理を迂回してはならない。**

利用可能なツールがなければ未接続として静的評価と未実行の改善案を完成させ、接続・有効化はユーザーに案内する。既存の設定ファイルがあっても代替接続には使わない。

レビューのみならクエリは実行しない。実行も依頼された場合は、その対象・期間で読み取りを進める。E2M作成、収集・アラート・ダッシュボードの設定変更は、別途変更依頼を受けた場合に行う。

## 目的を保つ改善を選ぶ

- **対象と期間を合わせる**：アカウント、イベント型、サービス、実効時間範囲を確認する。通常NRQLのSINCE省略時は直近1時間。ダッシュボードやツール引数の上書きも確認する。アラートは集約ウィンドウと評価設定を見る。
- **大きい処理を先に確認する**：広いLog/Span、先頭ワイルドカードの本文検索、正規表現、高カーディナリティのFACET・uniques()・uniqueCount()、JOINやサブクエリを調べる。構造化属性、対象範囲、必要な精度・粒度から改善する。
- **反復を減らす**：同じ母集団への複数集計をまとめ、取得済み結果と安定したメタデータを再利用する。HTTPリクエスト数と内包するNRQL実行数は別に数える。
- **必要な情報を返す**：SELECT属性とLIMITを目的に合わせる。通常のSELECT *はLIMIT省略時100件、FACETは既定10件。LIMIT MAXも全件取得ではない。全件が必要なら取得漏れを確認し、応答量と検査件数・CCUを別々に計測する。
- **意味を照合する**：期間、母集団、分母、単位、ゼロとnull、欠測、FACETの選出対象、時系列粒度を維持する。Metricへの置換は、集計定義と必要な属性が合う場合に選ぶ。backtickや除算だけでは負荷を判定できない。

## 実行計画と検証

既存結果・スキーマを優先し、必要な場合だけ短い範囲で確認する。計画には予定実行数、追加実行で解く疑問、終了条件を含める。対象アカウントやデータ型の総当たりは避ける。

探索期間と最終的な分析期間を分ける。必要期間が30日なら、短い探索結果で最終回答を代用せず、要求された期間で評価する。比較は同じ固定期間で行い、実効開始・終了時刻が返る場合は照合する。Metric・TIMESERIESの時間範囲の丸めにも注意する。

タイムアウトで状態が不明なら、対応ツールがある場合は既存の実行状態を先に確認する。再試行や範囲拡大は、未解決の疑問があり、事前の実行数・待機時間の上限内にある場合に行う。

## 判定と出力

- **効率的**：目的に見合う範囲と実行数を示す。
- **改善余地あり**：同じ答えを保てる改善と、確認した同等性を示す。
- **高負荷の懸念**：負荷要因と、その分析に必要な理由・削減時に失う情報を示す。
- **判断材料不足**：評価できる部分を答え、必要な対象・目的・頻度等をユーザーに確認する。

```text
判定：効率的／改善余地あり／高負荷の懸念／判断材料不足
理由：対象・期間・処理・実行回数から説明
改善案：クエリまたは実行計画。維持する結果と適用条件
検証状況：実行済み／未実行、同等性、計測値と残る不確実性
```

静的判断は静的評価と明記する。計測があれば同条件のbefore/afterを表にし、結果行数・実行時間・検査イベント数・スキャン量・記録CCUを区別する。未取得のCCU・金額・削減率は未測定とする。Core CCU、Advanced CCU、外部LLM料金は分け、MCP利用だけを理由にaCCUを加算しない。金額換算には対象契約の単価・課金条件が必要。
