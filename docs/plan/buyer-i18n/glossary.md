# buyer-i18n — 용어집

바이어 공간(`klow.kr/`) 번역의 **정본 용어 대응표**다. 두 곳이 이 표를 따른다.

- **UI 문구** — klow_web `src/i18n/kb/{ja,zh,vi,th,id,ru,ar}.ts` (Claude 직접 번역, D5)
- **DB 데이터** — klow_server `modules/buyer/buyer-glossary.ts` 가 이 표의 **미러**이고, LLM 프롬프트에 그대로 들어간다(D6)

⚠️ 이 표를 고치면 **서버 미러도 같이** 고친다. 미러가 어긋나면 화면의 UI 문구와 제품 설명이 같은 개념을 다른 말로 부른다.
서버 미러가 바뀌면 원문 해시는 그대로라 **기존 캐시는 다시 번역되지 않는다** — 새로 번역되는 것부터 맞는다.

## 1. 번역하지 않는 것 (원문 그대로)

| 대상 | 예 |
|---|---|
| 서비스·제품명 | `KLOW`, `KLOW Wholesale`, `KLOW Concierge`, `K-beauty` |
| 업계 약어 | `MOQ`, `SPF`, `PA++++`, `INCI`, `CPNP`, `FDA`, `GMP`, `EMS`, `DHL`, `PCI DSS` |
| 고유명사(D7) | 브랜드명, 제품명, 전성분(INCI), 회사명 `Welkit`, 도시 `Seoul` 은 각 언어 관용 표기(아래 표) |
| 숫자·단위·통화 | `50 ml`, `5%`, `USD`, `$`, `×` — 서아시아 숫자 대신 **서양 숫자 0-9** (ar 포함) |
| 자리표시자 | `{n}`, `{name}`, `<b>…</b>` 같은 태그는 위치만 옮기고 글자는 그대로 |

## 2. 핵심 용어

| en | ja | zh | vi | th | id | ru | ar |
|---|---|---|---|---|---|---|---|
| wholesale | 卸売 | 批发 | bán sỉ | ขายส่ง | grosir | опт / оптовый | الجملة |
| wholesale price | 卸価格 | 批发价 | giá sỉ | ราคาส่ง | harga grosir | оптовая цена | سعر الجملة |
| wholesale tiers | 数量別卸価格 | 阶梯批发价 | bậc giá sỉ | ราคาส่งตามจำนวน | tingkat harga grosir | оптовые уровни цен | شرائح أسعار الجملة |
| retail price / value | 小売価格 | 零售价 | giá bán lẻ | ราคาขายปลีก | harga eceran | розничная цена | سعر التجزئة |
| sample | サンプル | 样品 | mẫu thử | สินค้าตัวอย่าง | sampel | образец | عيّنة |
| sample box | サンプルボックス | 样品箱 | hộp mẫu thử | กล่องสินค้าตัวอย่าง | kotak sampel | набор образцов | صندوق العيّنات |
| sample request | サンプル依頼 | 样品申请 | yêu cầu mẫu thử | คำขอสินค้าตัวอย่าง | permintaan sampel | запрос образцов | طلب العيّنات |
| unit (수량) | 個 | 件 | sản phẩm | ชิ้น | unit | шт. | وحدة |
| reorder | 再注文 | 补货 | đặt lại | สั่งซื้อซ้ำ | pesan ulang | повторный заказ | إعادة الطلب |
| buyer | バイヤー | 采购商 | nhà thu mua | ผู้ซื้อ | pembeli | закупщик | المشتري |
| verified buyer | 認証済みバイヤー | 认证采购商 | nhà thu mua đã xác minh | ผู้ซื้อที่ยืนยันแล้ว | pembeli terverifikasi | проверенный закупщик | مشترٍ موثَّق |
| brand | ブランド | 品牌 | thương hiệu | แบรนด์ | merek | бренд | علامة تجارية |
| verified brand | 認証ブランド | 认证品牌 | thương hiệu đã xác minh | แบรนด์ที่ผ่านการตรวจสอบ | merek terverifikasi | проверенный бренд | علامة تجارية موثَّقة |
| collection | コレクション | 精选系列 | bộ sưu tập | คอลเลกชัน | koleksi | коллекция | المجموعة |
| distributor | 販売代理店 | 经销商 | nhà phân phối | ผู้จัดจำหน่าย | distributor | дистрибьютор | موزِّع |
| retailer | 小売店 | 零售商 | nhà bán lẻ | ร้านค้าปลีก | peritel | розничный продавец | تاجر تجزئة |
| export documents | 輸出書類 | 出口单证 | chứng từ xuất khẩu | เอกสารส่งออก | dokumen ekspor | экспортные документы | مستندات التصدير |
| business registration certificate | 事業者登録証 | 营业执照 | giấy chứng nhận đăng ký kinh doanh | หนังสือรับรองการจดทะเบียนธุรกิจ | sertifikat pendaftaran usaha | свидетельство о регистрации компании | شهادة السجل التجاري |
| under review | 審査中 | 审核中 | đang xét duyệt | อยู่ระหว่างตรวจสอบ | sedang ditinjau | на проверке | قيد المراجعة |
| quote | 見積もり | 报价 | báo giá | ใบเสนอราคา | penawaran harga | коммерческое предложение | عرض سعر |
| request (문의·요청) | リクエスト | 申请 | yêu cầu | คำขอ | permintaan | запрос | طلب |
| sign in / sign up | ログイン / 新規登録 | 登录 / 注册 | đăng nhập / đăng ký | เข้าสู่ระบบ / สมัครสมาชิก | masuk / daftar | войти / регистрация | تسجيل الدخول / إنشاء حساب |
| checkout | ご注文手続き | 结算 | thanh toán | ชำระเงิน | checkout | оформление заказа | إتمام الطلب |
| free shipping | 送料無料 | 免运费 | miễn phí vận chuyển | จัดส่งฟรี | gratis ongkos kirim | бесплатная доставка | شحن مجاني |
| shipping from Seoul | ソウルから発送 | 从首尔发货 | gửi từ Seoul | จัดส่งจากโซล | dikirim dari Seoul | отправка из Сеула | الشحن من سيول |
| referral | 紹介 | 推荐 | giới thiệu | การแนะนำ | referal | рекомендация | الإحالة |
| Seoul | ソウル | 首尔 | Seoul | โซล | Seoul | Сеул | سيول |
| Korea / Korean | 韓国 | 韩国 | Hàn Quốc | เกาหลี | Korea | Корея / корейский | كوريا / كوري |

카테고리 표시명은 소비자 화면 쇼핑 바(`labels.category.*`)·서버 `category-presets.ts` 의 기존 번역을 따른다.

### 2-1. 검색어 (SEO — 2026-10-19)

제목(`pages.*.metaTitle`·`pages.layout.title`)·H1(`pages.home.heroKicker`·목록 `title`)에는 **그 나라 바이어가 실제로 치는 말**을 쓴다. 본문은 위 표 그대로 두되, 아래 칸에 "K-beauty" 외래어나 `韩国美妆`·`ความงามเกาหลี`·`kecantikan Korea` 를 넣지 않는다 — 검색량이 작다.

| en | ja | zh | vi | th | id | ru | ar |
|---|---|---|---|---|---|---|---|
| Korean cosmetics wholesale | 韓国コスメ 卸・仕入れ | 韩国化妆品批发 | mỹ phẩm Hàn Quốc bán sỉ | ขายส่งเครื่องสำอางเกาหลี | grosir kosmetik Korea | корейская косметика оптом | مستحضرات التجميل الكورية بالجملة |
| Korean skincare | 韓国スキンケア | 韩国护肤品 | chăm sóc da Hàn Quốc | สกินแคร์เกาหลี | skincare Korea | средства по уходу за кожей | منتجات العناية بالبشرة |

## 3. 어조

| 언어 | 규칙 |
|---|---|
| ja | です・ます体. 버튼·라벨은 체언 종결(「サンプルを依頼」) |
| zh | 简体, 존칭 `您`. 버튼은 동사구(「申请样品」) |
| vi | `bạn`(B2B 이지만 UI 길이 때문에 `Quý khách` 은 쓰지 않는다) |
| th | 정중체, 문장 끝 `ครับ/ค่ะ` 는 쓰지 않는다(성별 중립) |
| id | `Anda`(대문자 A) |
| ru | `вы` 소문자. 버튼은 동사 원형(「Запросить образец」) |
| ar | 현대 표준 아랍어(MSA), 정중한 2인칭. 레이아웃은 LTR 유지(D8) — 문장부호만 아랍어(`،` `؟`) |

## 4. 점검

- 번역마다 **역번역**으로 의미가 바뀌지 않았는지 본다
- 라벨·칩·버튼은 영어보다 **눈에 띄게 길어지지 않게** 쓴다(th·ru·vi·id 가 특히 길어진다)
- About 그룹의 사업자 정보·배송·결제 조건(2026-10-15 "확인된 사실만")은 **숫자·기간·회사명을 원문과 대조**한다. 원어민 1회 검수를 권고한다
