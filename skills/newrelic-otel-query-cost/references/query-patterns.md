# 意味を保つクエリ改善

例は未実行の構文案。属性・値を実スキーマに合わせ、関数の意味は[公式NRQL仕様](https://docs.newrelic.com/docs/nrql/nrql-syntax-clauses-functions/)で確認する。

ログ属性は例示。service.name・level・trace.idの実在と値を確認する。severity属性は収集経路に合わせる。

## 特定サービスのエラーログを探す

目的がcheckoutサービスの直近30分のエラー調査なのに、全Logを7日間取得するなら範囲が過大。

```sql
FROM Log
SELECT timestamp, message, level
WHERE service.name = 'checkout' AND level = 'ERROR'
SINCE 30 minutes ago
LIMIT 50
```

service.nameとlevelが存在するか、実値がERRORかを確認する。50件は調査用の抜粋であり、全エラー件数ではない。時間範囲が7日必要な依頼なら30分へ勝手に短縮しない。LIMITは応答量の制御として説明する。

## filter()の書き換え

```sql
FROM Log
SELECT filter(count(*), WHERE level = 'ERROR'), count(*)
WHERE service.name = 'checkout'
SINCE 1 hour ago
```

エラー条件を外側WHEREへ移すと2つめのcount(*)もエラーだけになり、分母が変わる。この形を非効率という理由だけで書き換えない。単独のfiltered countでも、該当なしの0とnullの差やFACETが消える影響を評価する。

## 反復調査の計画を絞る

たとえば同じ対象・期間でtrace種類数と件数を別々に実行しているなら、次のような単一クエリが候補になる。

```sql
FROM Log
SELECT uniqueCount(trace.id), count(*)
WHERE service.name = 'checkout'
SINCE 1 hour ago
```

同じ集計結果・母集団かを確認する。データ量やCCUが必ず半分になるとは説明しない。取得済み結果で次の仮説が解けるなら再取得しない。GUID等の安定したメタデータはセッション中再利用し、障害発生後に変わり得る値を古いキャッシュで代用しない。

## Span、FACET、TIMESERIES

具体的なトレースIDが分かれば、その属性の実名を確認して絞る。全Spanを長期間かつ複数の高カーディナリティ属性でFACETするより、対象サービス・発生時刻から必要範囲を決める。

FACETを上位20にする場合は全対象の一覧ではないと伝える。時系列は必要な検出粒度に合わせる。TIMESERIESを付ければ常に軽くなるとはしない。

## 既存Metric・E2M

[イベントからメトリクスへの変換](https://docs.newrelic.com/docs/data-apis/convert-to-metrics/analyze-monitor-data-trends-metrics/)は、高頻度で同じイベント集計を繰り返す場合の設計候補。置換するメトリクスの意味・集計関数・単位・フィルタを検証してから提案する。

E2M未作成なら「このMetricで実行できる」と答えず、作成が必要な代替案とする。userIdやtraceId等をすべてディメンションにして時系列を増やさない。取り込み・保持・追加機能の費用を含めた全体効果は別途検証する。

## NRQLアラート

[NRQLアラート](https://docs.newrelic.com/docs/alerts/create-alert/create-alert-condition/create-nrql-alert-conditions/)のクエリへSINCE、UNTIL、TIMESERIES、LIMITを機械的に追加しない。集約・スライド・遅延設定と必要な検出時間を確認する。コスト削減のために重要な信号や監視範囲を黙って削らない。

## LIMIT MAXとFACETの取りこぼし

`FROM Log SELECT * SINCE 1 day ago LIMIT MAX`は全件エクスポートではない。公式仕様の現在の上限は5,000件で、FACETの既定は10件。上限値は利用時に公式仕様で再確認する。件数を知る目的なら同じ母集団の`count(*)`、全件の原文が必要なら取得方法・分割範囲を別途検討する。件数集計は原文取得の代替ではない。

次の2本をまとめる場合、FACETは通常SELECTの最初の集計で選ばれるため、「件数の上位」と「trace種類数の上位」は同じサービスとは限らない。

```sql
FROM Log SELECT count(*) FACET service.name SINCE 1 hour ago LIMIT 10
FROM Log SELECT uniqueCount(trace.id) FACET service.name SINCE 1 hour ago LIMIT 10
```

件数の上位10サービスにtrace種類数も添える目的なら結合できるが、両方のランキングを残す目的では同等としない。

## 固定期間による比較

[時間範囲](https://docs.newrelic.com/docs/nrql/using-nrql/query-time-range/)が相対指定の`SINCE 1 hour ago`では、順番に実行すると母集団が動く。比較用の例は次のようにタイムゾーン付きで固定し、実際の依頼期間へ置き換える。

```sql
FROM Log
SELECT uniqueCount(trace.id), count(*)
WHERE service.name = 'checkout'
SINCE '2025-01-01T10:00:00+09:00'
UNTIL '2025-01-01T11:00:00+09:00'
```

Metricの集約境界やTIMESERIESのバケット境界による時間範囲の丸めも確認する。TIMESERIESは最大366バケットで、例えば24時間を1秒刻みにする案はそのまま実行できない。必要な解像度を確認して粒度または分割を提案し、分割時のクエリ増加も計画に含める。

## ログ本文検索・正規表現

`message LIKE '%timeout%'`のような先頭ワイルドカードや`RLIKE`による本文検索は、対象が広いと確認するデータが大きくなる。先にサービス・期間・環境・level等の存在する構造化属性で対象を絞る。

エラーコードの属性がある場合は、その完全一致が目的のエラー集合と一致するか確認する。本文検索をlevelだけに置き換えると、必要なエラーを落としたり別のエラーを加えたりすることがある。ログの表記・大文字小文字・正規表現のマッチ範囲も維持する。

`SELECT * FROM Log`は通常、LIMIT省略時に100件までの抜粋を返す。必要な属性と明示的な件数を選び、検索した全件数と取り出したログ本文の件数を分けて説明する。

## uniques()とuniqueCount()の使い分け

- 一覧が目的なら`uniques()`を検討し、関数自身の取得上限とFACETごとの件数を確認する。外側のLIMITだけでは返る配列の大きさを制御できない。
- 種類数が目的なら`uniqueCount()`を検討する。高カーディナリティでは近似や精度指定の影響を確認し、必要な正確性と比較条件を維持する。
- userId・traceId等をFACETとuniques()で組み合わせる場合は、返却量と必要な分析軸を確認する。種類数へ置き換える案は、一覧自体が必要な調査の同等な代替にはならない。
