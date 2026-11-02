# 繰り返し調査の運用ノウハウ

## 消費量の大きい対象から着手する

利用量全体を見直す依頼では、クエリを片端から書き換える前に、どの機能に消費が集中しているか確認する。単一クエリのレビューだけなら、この全体調査は省く。

```sql
FROM NrConsumption
SELECT sum(consumption) AS coreCCU
WHERE metric = 'CoreCCU'
FACET dimension_productCapability
SINCE 1 day ago
LIMIT 20
```

- 同じ期間の`TIMESERIES 1 hour`を加えると、常時発生する消費と一時的な増加を分けて見られる。
- 利用者別に確認する必要があるときは、存在を確認した`dimension_userId`をFACETに使う。利用者IDが付かない処理もあるので、利用者別の合計を全体の合計と決めつけない。
- LIMITによる上位の抜粋と、分類属性のない記録を区別する。全体との差を確認したい場合は、同じ期間でFACETなしの合計と照合する。
- 機能別の内訳は改善対象を選ぶための値であり、そのまま単一MCP呼び出しの消費量にはしない。Advanced CCUは別枠で集計する。
- 消費の大きさだけで監視を止めない。利用目的・実行頻度・重複・維持する必要のある信号を確認して改善候補を選ぶ。

## サイト性能の初期診断を2本にまとめる

ブラウザの表示指標とバックエンドの状態を知りたいときは、PageViewTimingの複数集計を1本、対象の収集元に合うバックエンドメトリクスの複数集計を1本にまとめる。異なるイベント型の結果を無理に1本へ混ぜず、それぞれの母集団を維持する。

表示指標はtimingNameの条件を各集計に残し、サンプル数も一緒に取得する。

```sql
FROM PageViewTiming
SELECT filter(percentile(largestContentfulPaint, 75),
         WHERE timingName = 'largestContentfulPaint') AS lcpP75Seconds,
       filter(count(largestContentfulPaint),
         WHERE timingName = 'largestContentfulPaint') AS lcpSamples,
       filter(percentile(firstContentfulPaint, 75),
         WHERE timingName = 'firstContentfulPaint') AS fcpP75Seconds,
       filter(count(firstContentfulPaint),
         WHERE timingName = 'firstContentfulPaint') AS fcpSamples,
       filter(percentile(windowLoad, 75),
         WHERE timingName = 'windowLoad') AS loadP75Seconds,
       filter(count(windowLoad),
         WHERE timingName = 'windowLoad') AS loadSamples
WHERE (pageUrl = 'https://example.com/app'
       OR pageUrl LIKE 'https://example.com/app/%')
  AND timingName IN ('largestContentfulPaint', 'firstContentfulPaint', 'windowLoad')
SINCE 1 hour ago
```

対象URLと期間を置き換え、必要ならBrowserアプリも限定する。バックエンドは対象の計装に合うデータでサービスと期間を合わせる。Browserデータは独立に存在を確認する。最適化前後の比較では固定期間を使い、各指標のpercentile・単位・サンプル数まで照合する。ページ表示の指標とAPI応答時間は別の値として読む。

少数サンプルのpercentileだけでサイト全体を良好と評価しない。INPがなければ欠測として残し、別の表示指標で代用しない。CLSは記録時点で値が異なるため、異なるtimingNameのスナップショットを混ぜてページ終了時の値と扱わない。

## ダッシュボードは1回の軽さと実行回数を分けて見る

ウィジェットごとに、対象、実効期間、集計粒度、更新間隔、常時表示の有無を確認する。表示期間によって更新間隔も変わるため、期間を変える案は1回あたりの処理と更新回数の両方で比較する。

- 監視に必要な鮮度と履歴の長さを先に決める。更新回数を減らすためだけに、必要な直近の変化が埋もれる長期間へ広げない。
- 複数ウィジェットで同じ結果を重複取得していないか確認する。異なる対象や分母を持つウィジェットを、見た目が似ているだけで統合しない。
- アプリ別・環境別の似たダッシュボードは、テンプレート変数で管理をまとめる候補にする。変数化だけで実行数が減ったとは扱わず、実際の表示・更新状況を見る。
- TVモードのページ切替間隔と、チャートの更新間隔を混同しない。複数ページを1ページへ詰めるだけでクエリが減るとは判断しない。

## アラートはデータの到着特性に合わせる

頻繁かつ順序よく届くデータはEvent flow、疎なイベントやまとめて到着するデータはEvent timerを候補にする。イベント時刻の時系列だけでは到着順や取り込み遅延は分からないので、取り込みの状況も確認する。

集約ウィンドウ、遅延・タイマー、スライド間隔、欠損補完、信号喪失、検知までの許容時間を一緒に見る。窓を長くして処理を減らす案でも、短い異常が平均に埋もれたり検知が遅れたりするなら同等としない。

同じ信号の重複条件を整理する場合は、閾値だけでなく欠損時の扱いと通知先まで照合する。「最近発報していない」だけを理由に削除しない。

## 改善候補の一覧を出発点にする

利用できる環境ではCompute OptimizerのAlert Conditions／Dashboardsを確認し、消費量と改善候補から対象を絞る。元クエリと候補クエリを取得できる場合は、同じ固定期間で必要な結果が保たれるか比較する。

推定削減量は優先順位を付けるために使い、実測結果とは区別する。見積もりが空欄でも効果をゼロとは決めつけない。対象・分母・欠損・粒度を確認してから採否を決め、設定への反映は変更依頼がある場合に行う。
