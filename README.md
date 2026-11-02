# New Relic OpenTelemetry NRQL Cost Optimization

OpenTelemetryのOTLP送信向けに、必要な結果を保ちながらNRQLの対象・集計・実行回数を見直すAgent Skill。コミュニティ製で、New Relicの公式製品ではない。

スキル名：`newrelic-otel-query-cost`。データ選択は[判断手順](skills/newrelic-otel-query-cost/references/opentelemetry.md)を参照。

## 対象

OpenTelemetry SDK・Collector・NRDOTからNew RelicへOTLPで送るデータ。

共通のNRQL最適化・計測・NerdGraph・運用知識は、このリポジトリにも一式を保持する。他リポジトリやサブモジュールへの実行時依存はない。[別の収集経路向けスキル](https://github.com/seamoooo/newrelic-agent-nrql-cost-skills)は別名なので同時に導入できる。混在環境ではデータの収集元ごとに選ぶ。旧`newrelic-query-cost`と置き換える場合は、移行後に旧スキルの読込を解除する。

## 導入

macOS／Linuxの例。既存の同名スキルを確認してからコピーする。

```sh
git clone https://github.com/seamoooo/newrelic-otel-nrql-cost-skills.git
cd newrelic-otel-nrql-cost-skills
mkdir -p ~/.agents/skills
cp -R -i skills/newrelic-otel-query-cost ~/.agents/skills/
```

Codexで`$newrelic-otel-query-cost`を指定する。Claude Codeでは`~/.claude/skills/`へコピーして`/newrelic-otel-query-cost`、Copilot CLIでは`~/.copilot/skills/`へコピーし`/skills reload`後に`/newrelic-otel-query-cost`を指定する。

## 依頼例

```text
newrelic-otel-query-costで次のNRQLをレビューして。実行は不要です。
目的・対象サービス・必要期間を維持し、改善案と検証条件を示してください。
```

レビューはMCP接続不要。実行にはハーネスに公開されたNew Relic MCPツールと対象アカウントの権限が必要。資格情報を探索して直接接続する方法は使わない。

## 検証

Python 3.10以上。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate.py
.venv/bin/python scripts/validate_semantics.py
.venv/bin/python scripts/validate_otel_semantics.py
```

検証はパッケージ・内部リンク・合成データの集計を対象とする。実環境のNRQL・CCU、Claude Code／Copilot上の動作は未検証。[検証範囲](docs/validation.md)を参照。

## ライセンス

[MIT License](LICENSE)。[分割元](https://github.com/seamoooo/newrelic-nrql-cost-skills)の知識を収集経路別に整理した。
