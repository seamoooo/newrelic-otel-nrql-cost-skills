# 検証範囲

- `scripts/validate.py`：メタデータ、内部リンク、存在する場合は匿名化した数値台帳を検査。
- `scripts/validate_semantics.py`：合成データ4テストで、集計統合、エラーの分母、FACETの上位選出、欠測を検査。
- `scripts/validate_otel_semantics.py`：OTLP固有の合成データ12テスト。Histogram、単位、Span関連ID、サンプリング、DBサンプルと上位N件、重複計上を検査。

依存導入と実行コマンドは[README](../README.md#検証)。SQLiteでの意味の検査であり、NRQLエンジンの構文受理・実データの結果・CCUを検証するものではない。Claude Code／Copilot上の動作も未検証。

分割後の新しい仮想環境でオフライン検査は成功。独立した静的タスクでも、このリポジトリ内の参照だけで対象のデータ選択・サンプリング・分母を維持できることを確認した。実環境でのNRQL・CCUの計測は行っていない。
