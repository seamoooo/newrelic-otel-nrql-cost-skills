# OpenTelemetryのクエリ選択

OTLP送信のデータ選択と未実行のクエリ例。属性・単位はCollectorの変換や計装版により異なるため、実スキーマを優先する。

## 最初に送信経路を区別する

この文書のSpan・Log・MetricのマッピングはNew RelicへのネイティブOTLP送信が対象。[New RelicエージェントのOTel API対応](https://docs.newrelic.com/docs/apm/agents/manage-apm-agents/opentelemetry-api-support/)は、OTel APIで生成した情報をエージェントが取り込む別構成。OTel APIを使っているだけでTransaction・TransactionErrorを除外したり、duration.ms・trace.idを強制したりしない。エージェントの種類・バージョンと保存後の実スキーマから選ぶ。

## 利用可能なデータから選ぶ

| 目的 | 選択候補 | 適用条件 |
|---|---|---|
| 応答時間・処理量の定期集計 | 生成済みAPMメトリクス、またはOTelのHTTP/RPCメトリクス | 実在するメトリクスとディメンション・集計定義を確認 |
| 個別リクエスト・カスタム属性の調査 | Span | サービス・期間・必要なspan.kindやtrace.idで限定 |
| ログ本文・トレースとの関連 | Log | severity属性・trace.id・span.idの有無を確認 |

[New RelicのOTel APM UI](https://docs.newrelic.com/docs/opentelemetry/get-started/apm-monitoring/opentelemetry-apm-ui/)はOTelデータからAPM用メトリクスを生成する。OTelだから`apm.service.*`がないとも、必ずあるとも決めつけない。既存のAPMクエリを使える場合でも、appNameやtransactionTypeを含むフィルタの実在と意味を確認する。HTTP/RPCメトリクス由来とSpan由来では母集団が異なり得る。非Webのmessagingメトリクスや処理内訳のoverviewはSpan由来になり得るため、「Metricなら未サンプリング」と判断しない。

生成APMメトリクスでは`transactionName`、対応するSpanでは`transaction.name`を確認する。元の`http.route`等の任意の属性が生成メトリクスへすべてコピーされるとは限らない。名前が同じ`apm.service.transaction.duration`でも単位は元データのs/ms/nsを引き継ぐため、APMエージェントの秒単位の例をそのまま流用しない。旧HTTPの`http.server.duration`と新HTTPの`http.server.request.duration`、旧RPCと新RPCの対応は、利用時の公式APMメトリクス生成条件と実データで確認する。クエリ可能な元メトリクスが必ず生成APMメトリクスへ変換されるわけではない。

サービス名だけで一意にならない場合は、実在するentity.guidやservice.namespace・環境属性等で対象を限定する。APMエージェントとの混在時は識別済みの収集元を分ける。同じ処理を表すAPMメトリクスと元のOTelメトリクスを加算しない。

## 「transactionを取得」の読み替え

ネイティブOTLP送信の個別トランザクションやtransaction traceを求める依頼は、`FROM Span`で扱う。OTel APM UIにTransactionsが表示されても、`Transaction`イベントが生成される根拠にはしない。エラー事例も`TransactionError`を前提にせず、対象Spanの`otel.status_code`と必要に応じて[SpanEventの例外情報](opentelemetry-data-model.md)を確認する。例外イベントの存在だけでエラーと判定しない。

- HTTP/RPCの受信リクエスト一覧：対象サービスのserver Spanを選ぶ。trace全体のrootだけに限定しない。
- メッセージ処理・バックグラウンド処理：consumer等のspan.kindに加え、操作・計装属性を確認し、目的の処理境界を選ぶ。すべてのconsumer Spanが1メッセージ／1トランザクションに対応するとは限らない。
- UIの特定transaction traceとの照合：`transaction.name`が付与されていれば利用する。これはトランザクションのroot Spanへの付与であり、trace全体のrootと同一とは限らない。Spanの`name`とUIのtransaction名を同一視しない。
- 全サービスをまたぐトレースの詳細：候補Spanの`trace.id`で絞り直す。サービス境界をまたぐ目的ならサービス条件を引き継いで他サービスのSpanを落とさない。取得上限による欠落を確認する。
- 全体の処理量・応答時間・エラー率：利用可能なMetricを優先する。個別Spanの取得を求める依頼をMetric集計だけで代用しない。

HTTP/RPCの候補一覧の例（サービス識別とspan.kindの実値を確認後に使う）：

```sql
FROM Span
SELECT timestamp, id, trace.id, parent.id, name, transaction.name,
       duration.ms, otel.status_code
WHERE service.name = 'checkout' AND span.kind = 'server'
SINCE 30 minutes ago
LIMIT 50
```

50件は観測リクエストの抜粋。混在や同名サービスがあれば実在するエンティティ・環境条件を加える。見つからなくてもTransactionイベントを名前違いで総当たりせず、対象期間・計装・サンプリングと利用可能なデータを確認する。

## HTTPサーバーメトリクスの集計をまとめる

`http.server.request.duration`が利用でき、単位が秒と確認できた場合の例：

```sql
FROM Metric
SELECT count(http.server.request.duration) AS requests,
       rate(count(http.server.request.duration), 1 minute) AS rpm,
       average(http.server.request.duration) AS latencySeconds
WHERE service.name = 'checkout'
SINCE 1 hour ago
TIMESERIES 5 minutes
```

Histogramの観測数を使う`count(メトリクス)`と、格納ポイントの`count(*)`を混同しない。`sum(メトリクス)`は応答時間の総和でありリクエスト数ではない。[OTLP Metricマッピング](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-metrics/)に従い、metricName・unit・型・temporalityと必要な属性を確認する。旧名のメトリクスを新名へ機械的に置換したり、新旧を加算したりしない。秒とミリ秒の比較は単位を合わせる。

エラー率も必要で、対象メトリクスの`error.type`が目的のエラーを表すと確認できた場合は、同じSELECTに次を追加できる。

```sql
100 * filter(count(http.server.request.duration), WHERE error.type IS NOT NULL)
  / count(http.server.request.duration) AS errorPercent
```

分母に正常リクエストを残す。欠測や分母0を0%と補完しない。HTTPステータスで定義したエラー集合との一致は別途確認する。メトリクスの`error.type`とSpanの`otel.status_code = 'ERROR'`は異なる信号なので、同じエラー率と断定しない。

## Spanで調べる場合

[OTLP Spanマッピング](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-traces/)では所要時間は`duration.ms`、トレースIDは`trace.id`。次はspan.kindの実値が`server`と確認できた場合の例。

```sql
FROM Span
SELECT average(duration.ms) AS latencyMs,
       count(*) AS observedServerSpans,
       filter(count(*), WHERE otel.status_code = 'ERROR') AS observedErrorSpans
WHERE service.name = 'checkout' AND span.kind = 'server'
SINCE 1 hour ago
```

全Spanを数えると内部処理・クライアント呼び出しも含む。server Spanでも全リクエストの保証にはならない。サンプリング方式・欠落・重複を確認し、件数は観測Span数として返す。率が必要なら観測Span内の率と明記し、サンプリング率の逆数を掛けて全体件数を推定しない。サービスのserver Spanには別サービスを親に持つものもあるため、parent.idがないrootだけへ狭める案は同等ではない。

Spanしかない環境でも調査は続けられる。全トラフィックの定期指標を求める目的に合わなければ、未取得と明示する。Metricへの置換は属性・分母・単位・サンプリングの同等性を確認してから採用し、E2Mや収集設定の変更は別途依頼がある場合に行う。

## OTLPログのエラー検索

[OTLP Logマッピング](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-best-practices-logs/)のseverity属性を使う候補：

```sql
FROM Log
SELECT timestamp, message, severity.text, severity.number, trace.id, span.id
WHERE service.name = 'checkout' AND severity.text = 'ERROR'
SINCE 30 minutes ago
LIMIT 50
```

severity.textの表記は実値に合わせる。levelからの置換は元の検索集合を保てる場合だけ行い、FATAL等を含める目的ならその条件も確認する。ログのサービス属性や関連IDが欠けている可能性を残す。50件は抜粋であり全エラー件数ではない。
