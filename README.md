# mon-rpi-infra

Raspberry Pi デジタルサイネージの Ansible インフラ管理

## 前提条件

- Raspberry Pi 4 + Raspberry Pi OS Bookworm (arm64)
- macOS に [Raspberry Pi Imager](https://www.raspberrypi.com/software/) と Ansible をインストール済み

## クイックスタート

### 1. SSH 鍵の準備

プロジェクト専用の鍵ペアが `keys/` にあることを確認（秘密鍵は gitignore 済み）:

```bash
# 初回のみ
ssh-keygen -t ed25519 -f keys/signage -N "" -C "signage@mon-rpi-infra"
```

### 2. WiFi 認証情報の設定

```bash
# vault パスワードがなければ生成
openssl rand -base64 32 > .vault_password

# 認証情報を編集
ansible-vault edit inventory/group_vars/all/vault.yml
```

### 3. SD カード作成

rpi-imager CLI でイメージ書き込み + 初期設定を自動注入:

```bash
./scripts/flash-image.sh rpi-signage-01
```

公式 OS リスト JSON から最新の Bookworm arm64 イメージ URL を自動取得する。
ローカルファイル指定も可能:

```bash
IMAGE=path/to.img.xz ./scripts/flash-image.sh rpi-signage-01
VARIANT=lite ./scripts/flash-image.sh rpi-signage-02
```

### 4. Ansible プロビジョニング

初回は簡易 WiFi または Ethernet で SSH 接続してから実行:

```bash
ssh -i keys/signage signage@rpi-signage-01.local

# ドライラン
ansible-playbook --check --diff playbooks/site.yml

# 実行
ansible-playbook playbooks/site.yml
```

### 5. Tauri アプリのデプロイ

```bash
cp /path/to/signage-app roles/kiosk/files/signage-app
ansible-playbook playbooks/deploy-app.yml
```

## Bluetooth シリアル接続

Ansible 実行後、Pi は Bluetooth SPP で接続可能（自動ログイン）。

1. macOS のシステム設定 > Bluetooth から Pi をペアリング
2. ターミナルで接続:

```bash
screen /dev/cu.<hostname>-SerialPort 115200
```

切断: `Ctrl+A` → `Ctrl+\` → `y`

## ホスト固有の設定

`host_vars/<hostname>.yml`:

```yaml
display_rotation: 90        # 0, 90, 180, 270
bt_device_name: "rpi-signage-01"
```

## ロール一覧

| ロール | 内容 |
|--------|------|
| `common` | 基本パッケージ、タイムゾーン |
| `bluetooth_serial` | Bluetooth SPP シリアル接続 (D-Bus API, 自動ログイン) |
| `wifi_enterprise` | WPA Enterprise (PEAP/MSCHAPv2) |
| `display` | ディスプレイ回転 (wlr-randr) |
| `kiosk` | Tauri アプリデプロイ + labwc 自動起動 |

## シークレット管理

| ファイル | Git | 内容 |
|---------|-----|------|
| `keys/signage.pub` | tracked | SSH 公開鍵 |
| `keys/signage` | **ignored** | SSH 秘密鍵 |
| `inventory/group_vars/all/vault.yml` | tracked (暗号化) | WiFi 認証情報 |
| `.vault_password` | **ignored** | Vault 復号キー |
