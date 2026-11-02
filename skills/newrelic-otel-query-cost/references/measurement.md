# MCPによる実測

既存のクエリ結果・計測値を優先し、利用量照会の実行数も管理する。MCPの戻り値にない計測値は補完しない。実行時間だけではCCU・請求額は分からない。

## 必要最小限のスキーマ確認

以下は対象アカウントでの存在を確認するための候補。NrComputeUsageの保持や属性を固定しない。メタデータ取得ツールがある場合はそちらも検討する。

```sql
FROM NrComputeUsage SELECT keyset() SINCE 30 minutes ago
```

結果にない属性を推測で生成しない。何も返らない場合、権限・保持・遅延・機能未対応の可能性を残す。無条件に30日へ拡大せず、追加確認で何が解決するかを示す。成功するまで名前違いのイベントを総当たりしない。

query、usage、productCapability（または対応する実属性）が確認できた場合に限り、対象のクエリ文字列や実行ID等で絞って利用量を調べる。次はqueryが完全一致する実行のまとまりを調べるテンプレートであり、置換前に実行しない。

```sql
FROM NrComputeUsage
SELECT sum(usage), count(*)
WHERE query = '<対象クエリの正確な文字列>'
SINCE 30 minutes ago
```

同じクエリの複数実行や他ユーザーの実行が含まれる可能性がある。実行ID・APIキーID・ユーザー・時刻など、実際に存在する属性で追加限定する。query文字列はMCPツールのJSON引数へ安全に渡し、シェルへ直接展開しない。認証情報や生イベントをリポジトリへ保存しない。検証の集計値を記録する場合は、環境・利用者の識別情報を取り除く。

usageの単位・イベントの意味と、1実行あたり何イベント出るかを確認する。count(*)は利用量イベント数であり、自動的にクエリ実行回数ではない。帰属できなければ、sum(usage)/count(*)を「1クエリのCCU」と呼ばない。

## クエリ性能の観測

MCPが結果行しか返さず実行時間や検査件数を省略している場合は、[公式辞書のNrdbQuery](https://docs.newrelic.com/attribute-dictionary/?event=NrdbQuery)を確認する。実測が必要なら対象アカウントで短い期間の`keyset()`を一度実行し、存在する属性だけで計測する。すでに戻り値に十分な計測値があれば追加照会しない。

`query`、`durationMs`、`inspectedCount`、`status`が確認できた場合のテンプレート：

```sql
FROM NrdbQuery
SELECT count(*) AS records, latest(durationMs) AS durationMs,
       latest(inspectedCount) AS inspectedCount, latest(status) AS status
WHERE query = '<対象クエリの正確な文字列>'
SINCE 30 minutes ago
```

クエリ文字列をNRQL文字列としてエスケープしたうえで、MCPのJSON引数へ渡す。JSONのエスケープだけではNRQL内の引用符を処理できない。複数実行が含まれるならlatest()を合計値と見なさず、時刻や実在する識別属性で対応を確認する。観測期間は元データのSINCE/UNTILではなく、クエリを実行した時刻を含む期間にする。

NrComputeUsageでは実アカウントのクエリ属性が`dimension_query`等の場合もあるため、辞書の`query`をそのまま使えるとは限らない。確認済みの実属性へテンプレートを置き換え、`metric`とcompute種別で区分する。性能記録と利用量記録の両方が対象の実行に対応しているか確認する。

`inspectedCount`は検査イベント数、`durationMs`はクエリ実行時間であり、バイト単位のスキャン量でもCCUでもない。クライアントで測った往復時間はさらに別の値。MCP応答にはtextとstructuredContentで同じ内容が重複する場合があるので、結果JSONのサイズとMCP全体のサイズを区別する。

属性投影で応答量が減っても、検査イベント数や記録CCUは変わらない場合がある。集計統合は、別々のクエリの合計と統合後の値を比較する。単発・少量データの観測や記録CCUを、一般的な削減率・請求確定値・内部課金式として説明しない。

## 集計された請求対象利用量

全体の利用傾向が必要で、スキーマにconsumptionとmetricが確認できた場合の候補。必要なアカウントのデータだけを対象とする。

```sql
FROM NrConsumption
SELECT sum(consumption)
WHERE metric = 'CoreCCU'
SINCE 1 day ago
```

Advanced CCUが必要なら、別クエリまたは区分を保った集計でmetric = 'AdvancedCCU'を使う。アカウント全体の集計を特定MCP呼び出しのコストとは見なさない。集計の遅延・親子アカウントの重複・請求確定との差にも留意する。

参照：[公式の利用量クエリ](https://docs.newrelic.com/docs/accounts/accounts-billing/new-relic-one-pricing-billing/usage-queries-alerts/)、[NrComputeUsage辞書](https://docs.newrelic.com/attribute-dictionary/?event=NrComputeUsage)。

## 月初来の累積値

月初来の概算には、公式の利用量クエリに従って累積スナップショットの`latest()`を使う。`sum()`で複数時点の累積値を足さない。

```sql
FROM NrMTDConsumption
SELECT latest(consumption)
WHERE metric = 'CoreCCU'
SINCE 1 day ago
```

公式資料では利用料情報の生成に約3時間かかるため、直後の未反映をゼロ利用と断定しない。日・時間別の増分はNrConsumption、月初来はNrMTDConsumptionと区別する。[Consumption Management](https://docs.newrelic.com/docs/accounts/accounts-billing/new-relic-one-pricing-billing/consumption-management/)の適用対象プランも確認する。

## 比較方法

- 固定した同一期間、アカウント、母集団、集計定義でbefore/afterを比べる。変更していないクエリを比較のためだけに何度も再実行しない。
- 結果の同等性を確認してから、対応が取れたCCUやスキャン量を比べる。キャッシュ、トラフィック変動、課金記録の遅延は不確実性として残す。
- 削減率は同じ単位の実測beforeが正のときのみ `(before - after) / before × 100`。遅延の削減率をCCUの削減率として表示しない。
- 繰り返しの見込みは、観測済み1実行のCCU×予定実行数で概算できる場合に限る。全実行が同じ条件という仮定を明記する。金額には契約単価と無料枠・段階料金等が必要。
