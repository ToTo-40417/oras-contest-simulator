# 権利表示と第三者資料

## 非公式プロジェクト

ORAS コンテスト戦略シミュレーターは独立した非公式ファンプロジェクトです。任天堂株式会社、株式会社ポケモン、株式会社ゲームフリーク、株式会社クリーチャーズ、およびその他の関連企業は、本ツールの開発・配布・運営に一切関与していません。本ツールはこれらの企業の公認、提携、後援を受けていません。

ゲーム名、ポケモン名、技名などは、対応するゲームやゲーム内の項目を識別するために使用しています。第三者の商標その他の権利は各権利者に帰属します。配布物にはゲームROM、ROMから抽出した実行コード、画像、音声を含みません。

## ライセンスと出典

プロジェクト独自のコードとドキュメントには [LICENSE](LICENSE) の条件が適用されます。次に挙げる資料には各配布元の条件が適用されます。

| 資料 | 使用箇所 | 出典・通知 |
| --- | --- | --- |
| Ribbon Helper | 技、効果、コンボ、習得表の基礎データ | [取得時の公開データ](https://github.com/MercuryEnigma/ribbon-helper/tree/c22439f373be436cbf42d8ff484dde1fca503119/src/data) · [同梱ライセンス](oras_contest/data/LICENSE.ribbon-helper) |
| PokéAPI | 図鑑番号、技番号、ポケモン名、技名の照合 | [公開CSV](https://github.com/PokeAPI/pokeapi/tree/master/data/v2/csv) · [同梱ライセンス](oras_contest/data/LICENSE.pokeapi) |
| RFC 8682 | TinyMT32の仕様と参照ベクトル | [RFC](https://www.rfc-editor.org/rfc/rfc8682.html) · [同梱ライセンス](oras_contest/data/LICENSE.rfc8682) |
| Altissimo、Bulbapedia | NPCの出場条件、得点、技枠の参照 | [Altissimoの出場者表](https://altissimo1.github.io/Main-Series/ORAS/contest-opponents.html) · [Bulbapediaの出場者一覧](https://bulbapedia.bulbagarden.net/wiki/List_of_Contest_opponents_(Generation_VI)) |

### Ribbon Helper 由来データの範囲

`oras_contest/data/moves.json`、`effects.json`、`species.json`、`forms.json` の Ribbon Helper 由来部分と、その変換・補正部分は GPL-3.0 の扱いとします。ルートの非商用条件は、これらをGPLの条件で利用・再配布する権利に適用されません。混在する PokéAPI 由来部分には同梱のBSD通知も適用されます。

2026年11月23日の変換では、公開データをローカルJSONに正規化し、技・種族の名前と番号を照合しました。技の分類名を統一し、コンボ2組と妨害値1件を補正しました。技の説明文は削除しました。習得表は種族とフォームに分けて収録しています。元データの取得リビジョンと差分の再検査は [公開候補の監査記録](docs/release-audit.md) を参照してください。

NPC表は Altissimo の公開表を参照して作成し、Bulbapediaで照合した得点2件を採用しています。NPCの技枠順は4件を補正し、ニックネームは収録していません。これらの出典表示は原権利者の許諾取得を意味しません。
