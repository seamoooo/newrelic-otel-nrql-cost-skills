# OTelのデータモデルと調査時の落とし穴

ネイティブOTLP取り込みの型・関連ID・欠測を扱う。属性・型・対応機能は実データと利用時の仕様で照合する。

## 例外と非同期の関連をたどる

- Span自体の識別子は`id`、親は`parent.id`。Log・SpanEventの関連先は`span.id`。同じ名前へ統一して検索しない。
- [Span.eventsはSpanEventになる](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-traces/)。例外の詳細が必要なら対象Spanの`id`と`trace.id`からSpanEventを限定し、実在する`name`・`exception.type`・`exception.message`・`exception.stacktrace`等を選ぶ。例外イベントがなくてもstatusがERRORの場合があり、逆もある。エラー件数を例外イベント数に置き換えない。
- キューやバッチでは[span linksが別traceへの因果関係を表す](https://docs.newrelic.com/docs/distributed-tracing/ui-data/trace-details/#span-links)。同じtrace.id内やparent.idだけで全経路が得られるとは限らない。公開ツールや実在する保存形式でリンク先を確認し、リンク検索用のイベント型・属性名を推測しない。リンク先が未収集なら欠損として残す。リンク先の展開は必要な範囲と実行上限を定める。

## Metricの関数・単位・精度

[OTLP Metricマッピング](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-metrics/)と[New RelicのMetric型](https://docs.newrelic.com/docs/data-apis/understand-data/metric-data/metric-data-type/)で保存後の型を確認する。

| 入力と保存後の型 | クエリ改善時の判断 |
|---|---|
| monotonic Sum：deltaはcount、cumulativeはcumulativeCount | 増分の合計・rateと累積の現在値を区別する。取り込み時のdelta変換に重ねて差分を取らない。再起動・リセット・系列変更による欠測も確認 |
| non-monotonicのcumulative Sum：gauge | 最新値・平均・最大等を目的に合わせる。値を全期間足して処理件数と呼ばない。non-monotonic deltaはサポート対象外 |
| Histogram／ExponentialHistogram：distribution | count(metric)は観測数。average(metric)は観測数で重み付けされた平均。系列平均やバケット平均の単純平均へ置換しない |
| Summary：summary | OTLP summaryのquantileは未対応。特に一般的なcumulative summaryには制約があり、percentileへ置換できると仮定しない |

explicit bucket histogramは内部表現への補間を伴う。p95等は元のSpanから計算したpercentileと同等とは限らない。バケット幅・近似・精度を保つ。exemplarから個別traceへ関連付けられるとも仮定しない（確認時点でOTLP exemplarsは未対応）。unitがCollectorで削除されていたら、メトリクス名だけで単位を断定せず、receiver・変換の仕様や既存情報から確認する。

## ログ・イベント・時刻・属性

[OTLP Logマッピング](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-logs/)に従う。

- 通常のOTel EventもLogとして取り込まれる。`LogRecord.attributes`に`newrelic.event.type`が設定されていれば対応するCustom Eventになるため、Logで見つからないことだけで未収集としない。イベント名とNRDBイベント型を混同しない。
- 本文のJSON・mapの解析で属性が平坦化される場合がある。通常はtop-level > record/datapoint > scope > resourceの順で属性が優先され、Logでは本文解析で得た属性がさらに優先される。service.name等が想定と違う場合は変換・衝突を確認し、元のresource属性が必ず残るとは仮定しない。
- Logの元タイムスタンプがない場合は受信時刻がtimestampになる。Spanの開始時刻やMetricの観測区間と同じ時刻意味とは限らない。固定期間で比較するときは遅延・バッファ・時刻の由来を確認する。

## データがないとき

[OTLP endpoint](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp/)と[troubleshooting](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp-troubleshooting/)を参照する。取り込み成功応答でも内容検証は非同期で失敗し得る。属性数・長さ・型の制限で値が削除・切り詰めされることもある。NrIntegrationErrorが調査に必要なら実在する属性を確認して対象と期間を絞る。該当イベントがないことだけで取り込み成功を保証しない。

送信先リージョン・アカウントの不一致、サンプリング、filter/drop、カーディナリティ制限、収集間隔、再試行・queueの欠落を区別する。欠測を0件・正常0%へ変換しない。接続未公開のときは直接OTLP送信や資格情報の探索で補わず、未検証と報告する。

## 個別連携のクエリへ適用する

DB360のスナップショットと実行数、計画・サービス帰属、receiver別の集約済み値・重複収集は[個別連携の集計条件](opentelemetry-integrations.md)を必要時に参照する。

| 対象 | クエリに影響する違い・公式資料 |
|---|---|
| サービス・ホストの関連 | [Resources](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-resources/)でentity生成と関連付けを区別。service.nameの存在だけでhost/containerの関連まで保証しない。UIのタグをNRDBイベントの属性と同一視しない |
| Kubernetes | [インストール確認](https://docs.newrelic.com/docs/kubernetes-pixie/k8s-otel/install/)ではMetric・OtlpInfrastructureEvent・Logが対象。従来のK8sイベント型を仮定せず、cluster/namespace/pod等の実属性で限定 |
| Collector自身 | [Collector monitoring](https://docs.newrelic.com/docs/opentelemetry/collector-observability/collector-observability/)の内部テレメトリーと業務リクエストを区別。同じservice.nameでAttached Collectorの場合もある。receiver refusedは拒否を示すが上流のretryで回復し得る。queueへのenqueue失敗によるdropと、retryし得る送信失敗を区別する。内部テレメトリー未有効なら値を作らない |
| ATPのprocess.* | [ATP query](https://docs.newrelic.com/docs/opentelemetry/nrdot/atp/query/)のデータはフィルタ済み。観測プロセス数を全プロセス数とせず、filtering efficiencyをNRQLのCCU削減率と扱わない |
| Lambda | [欠測調査](https://docs.newrelic.com/docs/serverless-function-monitoring/aws-lambda-monitoring/opentelemetry/lambda-opentelemetry-troubleshooting/)のfaas.name/id/execution等を実スキーマで確認。同じservice.nameに複数関数が集約される場合もあり、必要な関数へ限定。HTTPのserver条件を全invocationへ流用しない |
| GenAI | [OTel AI monitoring](https://docs.newrelic.com/docs/ai-monitoring/opentelemetry-ai-monitoring/)の個別LLM・tool・agent処理はSpanの計装属性から選ぶ。server Spanだけへ絞ると子のLLM呼び出しを落とす。新旧gen_ai属性とtoken集計の定義を確認し、未収集の本文・token数をゼロで埋めない。LLM費用とCCUを分ける |

[取り込み量の管理](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-manage-data-ingest-volume/)にあるsampling・収集間隔・属性削除・temporality設定の変更は、NRQLだけの最適化とは別。元の観測対象・精度・鮮度を変えるため、変更依頼がない限り提案までとする。公式のサンプルクエリでも対象・期間・上限・型を照合し、無条件にコピーしない。
