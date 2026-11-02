# OTel個別連携の集計を保つ

DB360、receiver、Prometheus、プロキシ等で、保存されたデータの集計単位と収集条件を照合する。

## DB360のLogとAPM Span

query_sample/top_queryはLogの`event.name`で区分する。DB Metric、サーバーLog、APMのDB client Spanは異なる母集団。

- `db.server.query_sample`は収集時点のアクティブなセッション等のスナップショット。同じ実行が複数回現れ得る。`count(*)`をSQL実行数やAPM transaction数と呼ばない。
- `db.server.top_query`は収集ごとの上位N件の統計。Log行数と実行数を区別する。SQL Serverのexecution_count、PostgreSQLのcalls、MySQLのcount_star等は、該当receiverが出力する区間差分であることを確認して合計する。累積値やスナップショットの属性まで一律に差分・合計しない。
- 平均実行時間は、同じ対象・区間・単位の時間総和と実行数から加重平均する。各行の平均の単純平均へ置換しない。サーバー全体の統計と、アプリで採取したDB client Spanは母集団が違う。
- 収集側のtop N・フィルタ・権限・機能未有効による未収集は`LIMIT MAX`や期間拡大では復元できない。上位クエリだけの合計をDB全体と扱わない。

公式：[SQL Server](https://docs.newrelic.com/docs/opentelemetry/db360/mssql/metrics-reference/)、[MySQL](https://docs.newrelic.com/docs/opentelemetry/db360/mysql/metrics-reference/)、[PostgreSQL](https://docs.newrelic.com/docs/opentelemetry/db360/postgresql/metrics-reference/)、[Oracle](https://docs.newrelic.com/docs/opentelemetry/db360/oracle/metrics-reference/)。

### 実行計画・サービス帰属・DB範囲

- 実行計画は別の`db.server.query_plan` Logへ出力され、top_query/query_sampleから除かれる構成がある。計画属性が空でも計画未収集と即断しない。関連付けはインスタンス・DB・期間に加え、実在するquery ID・plan hash等を使う。SQL文字列やquery IDだけで全サーバーを横断しない。
- PostgreSQLはqueryidとuseridの組み合わせ等を確認。EXPLAINのgeneric planは実行時のactual planと同一ではなく、空で返るケースもある。MySQLのquery_planはJSON配列に包まれる形式で、plan hashがdigestと同値の設計もある。別の実行計画を一意に識別できると仮定しない。
- PostgreSQLの`pg_stat_statements`は正規化したSQLを集約し、SQL本文のコメントは最初の呼び出し元のものを保持する。top_queryの`db.query.comment_tags.nr_service_guid`だけで、全callsをそのサービスへ帰属させない。
- [APM–DB相関](https://docs.newrelic.com/docs/opentelemetry/db360/capabilities/db-apm/)のSQLコメント注入は対応New Relicエージェントの機能。純粋なOTel計装にもタグがあると仮定しない。プロキシ、DNSとIPの違い等でアドレスによる関連付けが成立しない場合もある。
- [PostgreSQL](https://docs.newrelic.com/docs/opentelemetry/db360/postgresql/multi-receiver/)の`databases`によるMetric対象と、query_sample/top_queryの`exclude_databases`による対象は異なる。必要なDBはLogの実在する`db.namespace`等でも限定する。複数インスタンスの導入成功表示だけでは、失敗・スキップした対象の収集を保証しない。

## receiverとPrometheusの違い

経路ごとの名前・型・ラベルを混ぜない。ドット区切りへの統一や、enumからbooleanへの変換を前提にしない。

| 対象 | 維持する意味 |
|---|---|
| [HAProxy](https://docs.newrelic.com/docs/opentelemetry/integrations/haproxy/metrics-reference/) | Prometheus変換の`haproxy.requests.rate`と`haproxy.connections.rate`は元の`*_rate_max`に対応し、生涯最大値。native receiverの現在rateと同等に扱わない。現在rateには適合するcounterと関数を選ぶ。frontend/backend/server各階層を合算して同じ通信を重複計上しない |
| [Kafka](https://docs.newrelic.com/docs/opentelemetry/integrations/kafka/metrics-reference/) | `.time.99p`等の計算済みpercentile gaugeから、全リクエストのp99を平均や再percentileで復元しない。topicのlag_sumとpartition別lag等、集約済み系列と内訳を二重に足さない |
| [RabbitMQ](https://docs.newrelic.com/docs/opentelemetry/integrations/rabbitmq/metrics-reference/) | `*_details.rate`等は既に毎秒のgauge。さらにrateをかけない。概説の名前と詳細表の名前が違う場合は実データを確認。queue/node/vhostの粒度も保つ |
| [NGINX](https://docs.newrelic.com/docs/opentelemetry/integrations/nginx/nginx-otel-metrics-reference/) | connections_currentは現在の状態別接続数。Sumという分類だけで累積counterと扱わない。active全体とreading/writing/waitingの内訳を重複加算しない |
| [Redis](https://docs.newrelic.com/docs/opentelemetry/integrations/redis/metrics/) | commandsは瞬間の毎秒値、commands.processedは総数。cmd.latencyのpercentile属性は分布そのものではない。複数ノードから報告するcluster全体の値をノード数分足さない。cluster機能の対応はreceiver版・経路で確認する |
| DBの時間・メモリ | MySQL Logのtimer_wait（秒）と対応Metricのnanoseconds、PostgreSQLのtotal_exec_time（ms）等を混ぜない。SQL Serverはプラットフォーム別資料に単位・型の違いもあり、名前だけで決定しない |

## 収集・エンティティ・欠測

- [IBM MQ Kubernetes](https://docs.newrelic.com/docs/opentelemetry/integrations/ibm-mq/kubernetes/)はターゲット分担なしの複数replicaやDaemonSetで重複scrapeを起こし得る。クエリ変更前に収集元と分担を確認する。replica数で割る、値だけでdedupする等で同等と断定しない。exporterのpollより短いscrapeで同じ区間統計を反復取得するケースも確認する。
- [IBM MQ](https://docs.newrelic.com/docs/opentelemetry/integrations/ibm-mq/metrics/)の`ibmmq_*`・`qmgr`・`queue`は保持し、`targetName`と`clusterName`は`target.name`と`cluster.name`へ変換する。この例外を「全ラベルをドット表記にする」と解釈しない。
- [Linkerd](https://docs.newrelic.com/docs/opentelemetry/integrations/linkerd/distributed-tracing/)のproxy SpanとアプリSpan、inbound/outboundのメトリクスは異なる観測地点。各サービスで選んだ処理境界を維持する。全server Spanや全proxyリクエストを足して業務リクエスト総数にしない。同じdeployment名へのservice.name変換で複数clusterが一つのentityへ統合される構成もある。
- [NGINX tracing](https://docs.newrelic.com/docs/opentelemetry/integrations/nginx/nginx-otel-distributed-tracing/)の同一entityにはendpointとdeployment名の一致が必要。[Elasticsearch](https://docs.newrelic.com/docs/opentelemetry/integrations/elasticsearch/distributed-tracing/)はSpanの`es.cluster.name`とMetricの`elasticsearch.cluster.name`を区別する。メトリクスと関連entityがあっても、アプリのend-to-end traceまで収集済みとは限らない。
- Redisはhostのaddress/port、Kubernetesのstable instance ID、cluster名という識別方法を区別する。filelog由来のLogには別途identityの付与が必要な構成があり、同じentityでLogが見つからないことだけでログ全体の未収集としない。
- remote DB collectorやECS Fargateでは、DB/コンテナメトリクスがあっても基盤hostのメトリクスはない場合がある。RDSの未対応・無効な指標の固定0、Oracleのlimit=-1（無制限）等を正常値や通常の分母へ変換しない。
- [Collector内部データ](https://docs.newrelic.com/docs/opentelemetry/collector-observability/collector-observability-setup/)の送信先は業務データと別accountの場合がある。[KubernetesのLowDataMode](https://docs.newrelic.com/docs/kubernetes-pixie/k8s-otel/advance-config/)やATPで落としたデータは、NRQLだけでは取り戻せない。
- [Lambda](https://docs.newrelic.com/docs/serverless-function-monitoring/aws-lambda-monitoring/opentelemetry/otel-service-name-lambda/)は`faas.name`を落とすとinvocationの認識・メトリクス生成が崩れる場合がある。同じservice名でもruntime別entityとなる場合や、名前変更前の履歴が旧entityに残る場合を確認する。ADOTに届かないX-Ray Spanをクエリ漏れと断定しない。

## Collector版の違いと費用

[NRDOTリリースノート](https://docs.newrelic.com/docs/release-notes/nrdot-release-notes/)は利用版に対応するものを読む。旧host/k8s distributionの廃止、file_log・host_metrics等への改名、JMX receiverの削除、DB receiver追加などがある。導入例の`latest`や古い設定名だけで、実際のコンポーネント・保存スキーマを保証しない。

[batch](https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/batchprocessor/README.md)は送信をまとめる処理であり、それだけで観測ポイント数・カーディナリティを減らす集約ではない。収集間隔の変更、属性削除、filter、samplingによる取り込み量の削減と、同じデータを照会するNRQLのCCU削減を区別する。Collector監視自体の取り込み・Core CCU等も業務クエリへ一括帰属させない。
