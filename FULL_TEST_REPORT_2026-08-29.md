# CompetitionAI 全量测试报告

> 生成时间：2026-08-29T15:32:20+08:00  
> 环境：Python 3.12.0 · macOS-26.6.1-arm64-arm-64bit  
> 主评测对象：FARM-RL 零依赖代理；稳定版作为对照。

## 1. 最终结论

- **正式总分：0.963000**（FARM，官方 200 会话 TechnicalScore）。
- 稳定版正式总分：0.958850；FARM 提升 **+0.004150**。
- FARM 正式集：Hit@10=1.000，MRR=0.978333，MTTC=2.525，Efficiency=0.8475。
- 200 条正式链路中，**7 条低于 0.9**，最低为 **0.710**。
- 改写压力集：FARM=0.909160，稳定版=0.923629，FARM 回退 **-0.014469**。
- 契约/对抗输入：稳定版 67/67、FARM 67/67；评测器单元测试 3/3。

正式总分只采用竞赛官方指标；契约通过率、鲁棒性和性能数据不与 TechnicalScore 人为混合。

## 2. 单条链路评分公式

每个用户问答到最终推荐的会话独立计分：

```text
命中：LoopScore = 0.50 + 0.30 / target_rank + 0.20 × (11 - hit_turn) / 10
未命中：LoopScore = 0
总分：200 条 LoopScore 的平均值
```

因此 Rank 1、第 3 轮命中的链路得 0.96；Rank 2、第 3 轮只有 0.81。

## 3. 正式端到端评测总览

| 方案 | 样本 | Hit@10 | MRR | MTTC | Efficiency | TechnicalScore | 状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| 稳定版 | 200 | 1.000 | 0.970833 | 2.620 | 0.8380 | 0.958850 | ✅ |
| FARM | 200 | 1.000 | 0.978333 | 2.525 | 0.8475 | **0.963000** | ✅ |

### 3.1 按场景的平均链路分

| 场景 | 样本数 | 稳定版 | FARM | 差值 | FARM 状态 |
|---|---:|---:|---:|---:|---|
| 购买型 | 80 | 0.969250 | 0.970375 | +0.001125 | ✅ |
| 浏览型 | 80 | 0.956375 | 0.961875 | +0.005500 | ✅ |
| 意图覆写 | 30 | 0.938000 | 0.948000 | +0.010000 | ✅ |
| 边界拒答 | 10 | 0.958000 | 0.958000 | +0.000000 | ✅ |

### 3.2 按难度的平均链路分

| 难度 | 稳定版 | FARM | 差值 | FARM 状态 |
|---|---:|---:|---:|---|
| easy | 0.969250 | 0.970375 | +0.001125 | ✅ |
| medium | 0.956556 | 0.961444 | +0.004889 | ✅ |
| hard | 0.938000 | 0.948000 | +0.010000 | ✅ |

## 4. 低于 0.9 的正式链路

下面严格按 `LoopScore < 0.9` 标记。`完整意图卡碰撞数`表示同一品类中具有完全相同四项公开意图字段的商品数。

| 标记 | Sample | 场景 | 难度 | Turn | Rank | 链路分 | 完整意图卡碰撞数 | 目标商品 |
|---|---|---|---|---:|---:|---:|---:|---|
| 🔴 | public_0020 | 购买型 | easy | 3 | 6 | **0.710** | 6 | Funny Saying Novelty Gift ideas - My Favorite People Call Me Grandma Long Sleeve T-Shirt |
| 🔴 | public_0076 | 浏览型 | medium | 3 | 4 | **0.735** | 8 | Proud Army Girlfriend US Flag Dog Tags Pride Military Lovers Zip Hoodie |
| 🔴 | public_0099 | 浏览型 | medium | 3 | 4 | **0.735** | 4 | Core 10 Women's Super Soft Fleece Straight Leg Jogger Sweatpant |
| 🔴 | public_0161 | 购买型 | easy | 3 | 2 | **0.810** | 4 | Thankful Grateful Blessed Shirt for Women Plaid Pumpkin Long Sleeve Tshirts Leopard Stripe Striped Thanksgiving Fall Tee Tops |
| 🔴 | public_0172 | 浏览型 | medium | 3 | 2 | **0.810** | 2 | Skechers Women's Sneaker |
| 🔴 | public_0175 | 浏览型 | medium | 3 | 2 | **0.810** | 9 | Ariat Men’s M2 Relaxed Boot Cut Jean |
| 🔴 | public_0054 | 购买型 | easy | 2 | 2 | **0.830** | 1 | Verdusa Women's Basic Casual Long Sleeve Round Neck Crop Top Pullover Sweatshirt |

最低链路是 **public_0020**：第 3 轮 Rank 6，得分 0.710。
主要薄弱点有两类：

1. 六条链路存在 2–9 个完整意图卡相同的商品，已披露字段不足以唯一定位，排序只能依赖弱先验。
2. `public_0054` 的完整意图卡本来唯一，但 FARM 小池门控在信息尚未全部披露时提前发布，目标只排到第 2；这是当前早发策略的明确副作用。

## 5. 改写鲁棒性压力测试

| 方案 | 输入 | Hit@10 | MRR | MTTC | Score | 状态 |
|---|---|---:|---:|---:|---:|---|
| 稳定版 | 原文 | 1.000 | 0.970833 | 2.620 | 0.958850 | ✅ |
| 稳定版 | 模板改写 | 0.990 | 0.885762 | 2.855 | 0.923629 | ✅ |
| FARM | 原文 | 1.000 | 0.978333 | 2.525 | 0.963000 | ✅ |
| FARM | 模板改写 | 0.985 | 0.839532 | 2.760 | 0.909160 | ✅ |

### 5.1 改写集按场景

| 方案 | 场景 | Hit@10 | MRR | MTTC | 场景分 | 状态 |
|---|---|---:|---:|---:|---:|---|
| 稳定版 | 购买型 | 0.988 | 0.923438 | 2.737 | 0.936031 | ✅ |
| 稳定版 | 浏览型 | 0.988 | 0.825342 | 2.675 | 0.907853 | ✅ |
| 稳定版 | 意图覆写 | 1.000 | 0.941667 | 3.600 | 0.930500 | ✅ |
| 稳定版 | 边界拒答 | 1.000 | 0.900000 | 3.000 | 0.930000 | ✅ |
| FARM | 购买型 | 0.988 | 0.861508 | 2.513 | 0.921952 | ✅ |
| FARM | 浏览型 | 0.988 | 0.795238 | 2.575 | 0.900821 | ✅ |
| FARM | 意图覆写 | 0.967 | 0.906667 | 3.833 | 0.898667 | 🔴 **< 0.9** |
| FARM | 边界拒答 | 1.000 | 0.816667 | 3.000 | 0.905000 | ✅ |

FARM 的改写意图覆写场景低于 0.9，说明字段签名和提前发布策略对非模板覆写语句仍不够稳健；在替换稳定提交前必须修复。

## 6. 契约、对抗输入与单元测试

| 测试 | 稳定版 | FARM | 结果 |
|---|---:|---:|---|
| 对抗消息、异常 profile、协议滥用、确定性 | 67/67 | 67/67 | ✅ 全通过，0 异常 |
| 评测器单元测试 | 3/3 | 同一评测器 | ✅ 全通过 |

单元测试覆盖：隐藏字段派生、miss 按第 11 轮计入 MTTC、推荐去重与顺序保持。

## 7. 性能基准

基准固定 `PYTHONHASHSEED=0`，对 100 个会话执行 400 次 `respond()`。性能数据不参与竞赛总分。

| 方案 | 冷启动 | p50 | p95 | p99 | max | LLM tokens |
|---|---:|---:|---:|---:|---:|---:|
| 稳定版 | 9.862s | 23.971ms | 25.973ms | 26.102ms | 26.182ms | 0 |
| FARM | 9.860s | 24.535ms | 26.596ms | 26.790ms | 27.455ms | 0 |

## 8. FARM 全部 200 条正式测试回路

| 状态 | Sample | 场景 | 难度 | Target | Turn | Rank | Hit | Efficiency | FARM 链路分 | 稳定版链路分 | 差值 | 商品标题 |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ✅ | public_0001 | 购买型 | easy | B09PYB7B6Z | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | QIAN0813 Celttic Knot Triple Moon Pentagram Pentacle Star Wicca Pendant Necklace Round Pagan Jewelry |
| ✅ | public_0002 | 意图覆写 | hard | B071X54486 | 3 | 1 | 1 | 0.80 | **0.960** | 0.810 | +0.150 | Hide & Drink, Rustic Handmade Full Grain Leather Men's Belt, Two Row Stitch Stylish Design - Everyday Belts for Men |
| ✅ | public_0003 | 意图覆写 | hard | B09YMTWDXJ | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Casio Men's Wrist Watch AQ-800E-7A |
| ✅ | public_0004 | 意图覆写 | hard | B07C2XPZ6D | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Emmalise Women's Basic Casual Long Camisole Adjustable Strap Cami Layering Top |
| ✅ | public_0005 | 购买型 | easy | B074G1JP8Z | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | GLOBALWIN Women's Waterproof Winter Boots Snow Boots For Women |
| ✅ | public_0006 | 浏览型 | medium | B071F2Z7JG | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Pro Club Men's Heavyweight Mesh Basketball Shorts |
| ✅ | public_0007 | 浏览型 | medium | B08PF98BV4 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | RITERA Plus Size Tops for Women Off the Shoulder Cold Shoulder Tops Short Sleeve Shirts Summer Blouses Sexy Tunics Tee XL-5XL |
| ✅ | public_0008 | 购买型 | easy | B0BPCC1KBT | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Hanes Womens Wireless Bra, Full-Coverage Pullover Stretch-Knit Bra, Smoothing T-Shirt Bra |
| ✅ | public_0009 | 购买型 | easy | B07GXHPWTJ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Angel Barcelo Roomy Fashion Hobo Womens Handbags Ladies Purse Satchel Shoulder Bags Tote Washed Leather Bag |
| ✅ | public_0010 | 购买型 | easy | B0929KL5W7 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | MANGOPOP Women's Mock Turtle Neck Long Sleeve Tops Bodysuit Jumpsuit |
| ✅ | public_0011 | 浏览型 | medium | B0BXP6MG3X | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Hanes Men's Tagless Cotton V-Neck Undershirt – Multiple Packs and Colors |
| ✅ | public_0012 | 浏览型 | medium | B08FFGQF72 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | GUBERRY Womens Wrap V Neck Long Sleeve Velvet Bodycon Ruched Cocktail Party Dress |
| ✅ | public_0013 | 意图覆写 | hard | B0C65TFM9F | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Vionic Women's Gemma |
| ✅ | public_0014 | 浏览型 | medium | B088QF5G58 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Hanes Men's Underwear Briefs Pack, Mid-Rise, Moisture-Wicking, 6-Pack |
| ✅ | public_0015 | 浏览型 | medium | B08513YB2T | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Crocs Unisex-Adult Classic Clog |
| ✅ | public_0016 | 浏览型 | medium | B07PH3X7QK | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Amazon Essentials Women's Lace-Up Combat Boot |
| ✅ | public_0017 | 购买型 | easy | B089RXP8K2 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Travelambo Womens Wallet RFID Blocking Bifold Multi Card Case Wallet with Zipper Pocket |
| ✅ | public_0018 | 购买型 | easy | B07H3T5YGH | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | O2TEE Men's Workout Gym Tank Tops Men - Custom Tank Top - Customized & Personalized Tanktops Text |
| ✅ | public_0019 | 浏览型 | medium | B076VQQ962 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Asgard Women's Ankle Rain Boots Waterproof Chelsea Boots |
| 🔴 | public_0020 | 购买型 | easy | B08P4SSFX4 | 3 | 6 | 1 | 0.80 | **0.710** | 0.710 | +0.000 | Funny Saying Novelty Gift ideas - My Favorite People Call Me Grandma Long Sleeve T-Shirt |
| ✅ | public_0021 | 浏览型 | medium | B07K4FX4WZ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Amazon Essentials Men's Slim-Fit Stretch Golf Pant |
| ✅ | public_0022 | 购买型 | easy | B08F5G843H | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | YESNO Summer Dresses for Women Casual Loose Bohemian Floral Dress with Pockets Spaghetti Strap Maxi Dress E75 |
| ✅ | public_0023 | 意图覆写 | hard | B08ZKFD4GM | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Hanes Women's Wireless Bra with Cooling, Seamless Smooth Comfort Wirefree T-Shirt Bra |
| ✅ | public_0024 | 购买型 | easy | B076X3JXMW | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Riviera Sun Womens Off Shoulder Embroidered Jumpsuit Romper |
| ✅ | public_0025 | 浏览型 | medium | B0BRS1DHVQ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | PRETTYGARDEN Women's Loose Solid Off Shoulder Elastic Waist Stretchy Long Romper Jumpsuit |
| ✅ | public_0026 | 购买型 | easy | B093R14VP1 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | ASICS Men's Gel-Venture 6 MX Running Shoes |
| ✅ | public_0027 | 购买型 | easy | B0858VDFDW | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Riders by Lee Indigo Women's Ultra Soft Denim Capri |
| ✅ | public_0028 | 购买型 | easy | B0B9ZYDDZ1 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Buffway Slim Minimalist Front Pocket RFID Blocking Leather Wallets for Men Women |
| ✅ | public_0029 | 购买型 | easy | B01IAKCZEK | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Sanuk Yoga Sling 2 Light Natural 5 B (M) |
| ✅ | public_0030 | 购买型 | easy | B09V5RTXG9 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | #followme Microfleece Men’s Buffalo Plaid Pajama Pants with Pockets |
| ✅ | public_0031 | 购买型 | easy | B0BQDTGHMZ | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Signature by Levi Strauss & Co. Gold Label Women's Modern Skinny Jeans (Standard and Plus) |
| ✅ | public_0032 | 购买型 | easy | B0834HZQZF | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | IZZY + TOBY 100% Cotton Nightgowns for Women Soft Ladies Gowns Sleepwear Long Sleeveless Nightgown |
| ✅ | public_0033 | 浏览型 | medium | B08134XNNB | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Women's Walking Shoes Sock Sneakers - Mesh Slip On Air Cushion Lady Girls Modern Jazz Dance Easy Shoes Platform Loafers |
| ✅ | public_0034 | 意图覆写 | hard | B07Q9PNNB5 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | DUOYANGJIASHA Loafers for Women Casual Slip on Dress Loafers Womens Comfortable Leather Driving Shoes Outdoor Walking Flats Shoes |
| ✅ | public_0035 | 边界拒答 | medium | B0BN6CCHB7 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Skechers Men's Go Max-Athletic Air Mesh Slip on Walking Shoe Sneaker |
| ✅ | public_0036 | 浏览型 | medium | B08BWR1T58 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | 47 Pairs Fashion Earrings for Women Girls, Boho Statement Tassel Rattan Leather Earrings Butterfly Acrylic Hoop Stud Drop Dangle Earrings Set, Hypoallergenic for Sensitive Ears |
| ✅ | public_0037 | 浏览型 | medium | B08KKBBMMD | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | The Children's Place Boys' Pull on Cargo Pants |
| ✅ | public_0038 | 意图覆写 | hard | B07B5RGY2N | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Blowfish Malibu Women's Fruit Sneaker |
| ✅ | public_0039 | 浏览型 | medium | B07TZCJW9X | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Women's Pro Series Cycling Short Sleeve Jersey, Cargo Bib Shorts, or Kit Bundle |
| ✅ | public_0040 | 浏览型 | medium | B08ZJWTCDR | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Champion Men's Joggers, Everyday Joggers, Lightweight, Comfortable Joggers for Men, 31" |
| ✅ | public_0041 | 边界拒答 | medium | B09MSY8926 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | LETDIOSTO Women's Plus Size Tops Casual Blouse Short Sleeve Lace Tunic Tops Fit Flare, M-4XL |
| ✅ | public_0042 | 购买型 | easy | B01LWOGORL | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Timex Men's Classic Digital Watch |
| ✅ | public_0043 | 浏览型 | medium | B0C1KNGLPX | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Levi's Women's Classic Bootcut Jeans |
| ✅ | public_0044 | 购买型 | easy | B09BQ4G5BD | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | K898 Men's Square Leg Swimming Jammer Shorts UPF50+,Men Swimsuit Swim Jammers Fabric Shape Retention |
| ✅ | public_0045 | 购买型 | easy | B07Z8NTWVV | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | HOCOSIT Women's Floral Print Short Ruffle Sleeve Pleated Front V Neck Button Tunic Tops |
| ✅ | public_0046 | 意图覆写 | hard | B0B42PVX1F | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Wool Plus Size Thigh High Socks For Thick Thighs- Extra Long Womens Warm Cable Knit Over Knee Stockings Leg Warmers |
| ✅ | public_0047 | 浏览型 | medium | B0BYZX7B1L | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Lunarable Multicolor Unisex Bandana |
| ✅ | public_0048 | 浏览型 | medium | B00VQBMJUQ | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Vizari Infinity FG Soccer Cleat (Toddler/Little Kid/Big Kid) |
| ✅ | public_0049 | 浏览型 | medium | B08G4WVYLJ | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Dacomfy Mens Slip On Shoes, Men's Loafers & Slip-ons Leather Walking Shoes for Men, Hand Stitching Comfortable Breathable Brown Black Khaki |
| ✅ | public_0050 | 边界拒答 | medium | B07BYR6T7W | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | EverBoots Mens Work Boots for Men, Leather EverFit Lightweight Comfort Boot, Anti Slip & Shock Absorption, Soft Oil Grain, Goodyear Welt, Industrial Construction, Roofing, Electrician Moc Toe Wedge |
| ✅ | public_0051 | 浏览型 | medium | B07N1624C5 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Skechers Women's Go Walk 5-True Sneaker |
| ✅ | public_0052 | 意图覆写 | hard | B09G2ZNZY4 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Grlasen Women's Zipper Summer Pleated Button Short Sleeve T-Shirt Summer V-Neck Solid Color Casual top |
| ✅ | public_0053 | 购买型 | easy | B07TZK3GZK | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Passport Holder Cover Travel RFID Blocking Passport Cover Rose Gold Cute Flowers Passport Wallet with Elastic Band for Women |
| 🔴 | public_0054 | 购买型 | easy | B08PP1ZJQ5 | 2 | 2 | 1 | 0.90 | **0.830** | 0.960 | -0.130 | Verdusa Women's Basic Casual Long Sleeve Round Neck Crop Top Pullover Sweatshirt |
| ✅ | public_0055 | 浏览型 | medium | B0C1TDJ9HZ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Crocs Unisex-Adult Baya Clogs, Neo Mint, 7 Women/5 Men |
| ✅ | public_0056 | 浏览型 | medium | B0B2RF64YD | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Amazon Essentials Men's Short-Sleeve Crewneck T-Shirt, Pack of 2 |
| ✅ | public_0057 | 浏览型 | medium | B085RX192V | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Crocs Women’s Freesail Clog |
| ✅ | public_0058 | 购买型 | easy | B08L83YQTZ | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | JTANIB Women Packable Rain Jacket Waterproof Lightweight Raincoat Hooded for Hiking Outdoor Travel |
| ✅ | public_0059 | 浏览型 | medium | B01H6DGA16 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Supplim Women's Body Shaper Waist Cincher Underbust Corset Bodysuit Shapewear |
| ✅ | public_0060 | 浏览型 | medium | B08R61K9B9 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Fruit of the Loom mens Woven Sleep Pajama Pant |
| ✅ | public_0061 | 购买型 | easy | B08HCP9YTV | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | 1pc Surgical Steel Piercing Ring for Nose Septum Cartilage Helix Tragus Conch Rook Daith Lobe 20g-18g-16g-14g-12g-10g 5mm-6mm-7mm-8mm-9mm-10mm-11mm-12mm-14mm-16mm Silver/Gold/Rose Gold/Black/Rainbow |
| ✅ | public_0062 | 浏览型 | medium | B015K51VPM | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | chouyatou Women's Casual Stretch Waist Washed Denim A-line Maxi Skirt |
| ✅ | public_0063 | 浏览型 | medium | B09MKL5TBK | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | BALEAF Womens' 7" Long Running Athletic Shorts with Liner Workout Zipper Pocket |
| ✅ | public_0064 | 意图覆写 | hard | B019DU687Q | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Memorose Womens Sexy Long Sleeve Cut-Out Bandage Bodycon Clubwear Midi Dress |
| ✅ | public_0065 | 购买型 | easy | B0BSQ9TCYC | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Arctix Women's Essential Insulated Bib Overalls |
| ✅ | public_0066 | 购买型 | easy | B0BFLFSB2Y | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | GRAPENT Women's Plus Size Sequin 3/4 Sleeves Evening Gown Party Long Maxi Dress |
| ✅ | public_0067 | 购买型 | easy | B09G9BXJZM | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | TLZC Men's Lightweight Bomber Jacket Windbreaker Slim Fit Active Coat Outerwear |
| ✅ | public_0068 | 意图覆写 | hard | B08SH8GF6K | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Skechers Women's Go Walk 6-Big Splash Sneaker |
| ✅ | public_0069 | 浏览型 | medium | B07ZFBQ76H | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Acrylic Earrings For Women Girls Statement Geometric Earrings Resin Acetate Drop Dangle Earrings Mottled Hoop Earrings Fashion Jewelry |
| ✅ | public_0070 | 浏览型 | medium | B010LVBVKA | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Travel Neck Wallet with RFID Blocking – Passport Holder Neck Pouch to Keep Your Cash And Documents Safe – Get Peace Of Mind When Traveling |
| ✅ | public_0071 | 意图覆写 | hard | B06XRFSDL4 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Mordenmiss Women's Loose Sweatshirt Spring/Fall Simple Shirt Tops |
| ✅ | public_0072 | 意图覆写 | hard | B09JG4V9ZR | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Facitisu Womens Winter Warm Jacket Long Down Faux Fur Hooded Quilted Sherpa Lined Coat |
| ✅ | public_0073 | 浏览型 | medium | B07QPM54V7 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | WNEEDU Women's Summer Casual T Shirt Dresses Short Sleeve Swing Dress with Pockets |
| ✅ | public_0074 | 浏览型 | medium | B07N15QTKC | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Skechers Women's Go Walk 5-Lucky Sneaker |
| ✅ | public_0075 | 浏览型 | medium | B08L13LJ5M | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | BULLIANT Men's Belt, Slide Ratchet Belt For Men Dress Pant Shirt Oxfords,trim To Fit |
| 🔴 | public_0076 | 浏览型 | medium | B07XT6PLTB | 3 | 4 | 1 | 0.80 | **0.735** | 0.735 | +0.000 | Proud Army Girlfriend US Flag Dog Tags Pride Military Lovers Zip Hoodie |
| ✅ | public_0077 | 浏览型 | medium | B077JDSZ27 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Ashford & Brooks Mens Flannel Long Sleeve Sleep Nightshirt |
| ✅ | public_0078 | 意图覆写 | hard | B0C5RLJDSF | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Hanes Women's Value, Crew Soft Moisture-Wicking Socks, Available in 10 and 14-Packs |
| ✅ | public_0079 | 浏览型 | medium | B0BFRMX3JG | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Jeasona Women’s Fuzzy Slipper Socks With Grippers Cozy Warm Cute Animal Gifts |
| ✅ | public_0080 | 意图覆写 | hard | B0BPRQY4CF | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | IZOD Men's Advantage Performance Short Sleeve Polo Shirt |
| ✅ | public_0081 | 浏览型 | medium | B0BSS36XCS | 3 | 1 | 1 | 0.80 | **0.960** | 0.810 | +0.150 | Fruit of the Loom Men's Eversoft Cotton Stay Tucked V-Neck T-Shirt |
| ✅ | public_0082 | 购买型 | easy | B09BPZCWDP | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | Hicarer 21 Pieces Surfer Wave Bracelet Ocean Wave Adjustable Waterproof Handmade Friendship Bracelet Summer Sunflower Bracelets Anklets Jewelry for Women Teen Girls |
| ✅ | public_0083 | 购买型 | easy | B0BPMCJ1RD | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | CHICZONE Plaid Shacket Jacket Womens Long Flannel Jacket Casual Lapel Button Down Tartan Trench Coats |
| ✅ | public_0084 | 意图覆写 | hard | B08WKZNFG2 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | BeltBro Titan No Buckle Elastic Belt For Men — Fits 1.5 Inch Belt Loops, Comfortable and Easy To Use |
| ✅ | public_0085 | 浏览型 | medium | B0C3YJMRRD | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | welltree Slides for Women Men Pillow Slippers Non-Slip Bathroom Shower Sandals Soft Thick Sole Indoor and Outdoor Slides |
| ✅ | public_0086 | 浏览型 | medium | B07WN8N9Q7 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | LongBay Women's Chenille Knit Bootie Slippers Cute Plush Fleece Memory Foam House Shoes |
| ✅ | public_0087 | 浏览型 | medium | B0BT158RRR | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Goodthreads Men's Standard-Fit Short-Sleeve Printed Poplin Shirt |
| ✅ | public_0088 | 购买型 | easy | B07Z6J5N6Y | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Amazon Essentials Women's Cotton Bikini Brief Underwear (Available in Plus Size), Multipacks |
| ✅ | public_0089 | 意图覆写 | hard | B0BXMCZLZV | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Vanity Fair Women's Perfectly Yours High Waisted Brief Panties |
| ✅ | public_0090 | 购买型 | easy | B07MGR6D5M | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | Mardi Gras Costume Accessory Mardi Gras Mesh Shimmering Scarf Purple Green Gold Scarf Masquerade Costume Mardi Gras Party Favor (Style 2) |
| ✅ | public_0091 | 浏览型 | medium | B0C5XB43GG | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | 925 Sterling Silver Small Hoop Earrings Cubic Zirconia Huggie Hoop Earrings, 3 Pairs 14K White Gold Plated Cartilage Piercing Earrings Ear Cuff Tiny Hoop Earrings for Women Men |
| ✅ | public_0092 | 浏览型 | medium | B07FKNZC43 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | COSOSA Womens Satin Striped Pajamas Long Sleeve V-neck Tops and Pants 2-piece Pj Set |
| ✅ | public_0093 | 购买型 | easy | B07PYB8F1G | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Hanes Women's Signature Breathe Cotton Brief Underwear 6-Pack |
| ✅ | public_0094 | 购买型 | easy | B01L99SW78 | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Ariat Fatbaby Western Boot – Women’s Leather Western Boots |
| ✅ | public_0095 | 购买型 | easy | B09N78FT2W | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Free Leaper High Waisted Yoga Pants with Pockets for Women-Comfortable Running Seamless Leggings |
| ✅ | public_0096 | 意图覆写 | hard | B074K2QX3M | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Zeagoo Women's Polka Dots Shirt Striped 3/4 Sleeve Casual Scoop Neck Tops Tee S-XXXL |
| ✅ | public_0097 | 购买型 | easy | B0785RCKBT | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Leggings Depot Women's Flared Casual, Work, Lounge Palazzo Pants-Wide Leg |
| ✅ | public_0098 | 浏览型 | medium | B08CZ34D75 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | adidas Men's Lite Racer Adapt 4.0 Running Shoe |
| 🔴 | public_0099 | 浏览型 | medium | B0971YMPCR | 3 | 4 | 1 | 0.80 | **0.735** | 0.735 | +0.000 | Core 10 Women's Super Soft Fleece Straight Leg Jogger Sweatpant |
| ✅ | public_0100 | 浏览型 | medium | B002OHE4D6 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Dockers Proposal - Genuine Full-Grain Leather Slip-On Loafer Dress Shoes for Men Featuring All Motion Comfort Technology, EVA Sock Lining, and Durable Rubber Outsole |
| ✅ | public_0101 | 购买型 | easy | B07QMS8TX8 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Medical Cargo Pants for Men Workwear Originals, Zipper Fly Scrubs for Men 4000 |
| ✅ | public_0102 | 浏览型 | medium | B07PWZXZVX | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | FallSweet Padded Push Up Lace Bras for 34A to 44C Underwire |
| ✅ | public_0103 | 意图覆写 | hard | B0BT8T2FQ3 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Fruit of the Loom Men's Eversoft Cotton Stay Tucked Crew T-Shirt |
| ✅ | public_0104 | 边界拒答 | medium | B00QSAICLU | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Black 1 Inch Wide Leather Like Headband Solid Hair band for Women and Girls |
| ✅ | public_0105 | 浏览型 | medium | B07Q46M2J2 | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | IUGA High Waisted Yoga Pants for Women with Pockets Capri Leggings for Women Workout Leggings for Women Yoga Capris |
| ✅ | public_0106 | 购买型 | easy | B0776SVXW9 | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Mens Socks Dress Cotton Socks Fashion Patterned Argyle Socks &Formal Business Socks Classic Cotton Dress Casual Socks for Men |
| ✅ | public_0107 | 购买型 | easy | B01KPFK9ZA | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | FASHION BOOMY Women's Zip Up Safari Military Anorak Jacket with Hood Drawstring - Regular and Plus Sizes |
| ✅ | public_0108 | 购买型 | easy | B01I21CI7G | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Hanes Women's Stretch Jersey Bike Shorts, Women’s Cotton Bike Shorts, Women’s Athletic Shorts, 7" Inseam |
| ✅ | public_0109 | 购买型 | easy | B016OT9D3K | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Hanes Men’s Short Sleeve Graphic T-shirt Collection |
| ✅ | public_0110 | 浏览型 | medium | B0C277G9FW | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Loritta 5 Pairs Womens Wool Socks Thick Knit Vintage Winter Warm Cozy Crew Socks Gifts |
| ✅ | public_0111 | 购买型 | easy | B07H7BWMQF | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Lacozy Women's Off Shoulder Long Sleeve Oversized Pullover Sweater Knit Jumper Loose Tunic Tops |
| ✅ | public_0112 | 边界拒答 | medium | B086ZNJY8K | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Nautica Men's Casual Slip-On Fashion Sneakers-Walking Shoes-Lightweight Joggers |
| ✅ | public_0113 | 浏览型 | medium | B08CTFPBN5 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | RockDove Women's Nomad Slipper with Memory Foam |
| ✅ | public_0114 | 购买型 | easy | B07H34Z5V6 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Athlefit Women's Wedge Sneakers Hidden Heel Platform Wedge Booties Hidden Wedgie Sneakers |
| ✅ | public_0115 | 浏览型 | medium | B08VWZBYPY | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | PrinStory Womens Sleepwear Short Sleeve Nightgown Soft Sleepshirt Pleated Nightshirt Scoopneck Casual Loungewear |
| ✅ | public_0116 | 购买型 | easy | B07S2Y3THP | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Lugz Men's Clipper Sneaker |
| ✅ | public_0117 | 购买型 | easy | B07HJ18QRQ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Vionic Sadie Women's Adjustable Strap Orthotic Slippers |
| ✅ | public_0118 | 购买型 | easy | B09M72C8PG | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Angerella Women Vintage Polka Dot High Waisted Bathing Suits Bikini Set |
| ✅ | public_0119 | 购买型 | easy | B0BBLR3QB2 | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | MIFORINES Ladies Summer Jelly Pillow-shaped Top Handle Handbag Candy Color Transparent Crystal Purse |
| ✅ | public_0120 | 浏览型 | medium | B08GPGX2QG | 3 | 1 | 1 | 0.80 | **0.960** | 0.810 | +0.150 | SENDEFN Wallets for Women Genuine Leather Credit Card Holder with RFID Blocking Large Capacity Wristlet |
| ✅ | public_0121 | 浏览型 | medium | B08HS712ZB | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Duufin 5 Pcs Lace Bralettes for Women Bralette Padded Lace Bandeau Bra |
| ✅ | public_0122 | 浏览型 | medium | B074KJ49F2 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Leggings Depot Premium Quality Women's Cotton Blend Stretch Pull-on Jeggings with Pockets |
| ✅ | public_0123 | 意图覆写 | hard | B07CZ84YFJ | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Lanzom Womens Classic Wide Brim Floppy Panama Hat Belt Buckle Wool Fedora Hat |
| ✅ | public_0124 | 购买型 | easy | B07TN1845M | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Arctic Air Adjustable Sports Cap, Beige, Hat |
| ✅ | public_0125 | 意图覆写 | hard | B07VCYFB5D | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Baseball Cap Custom Personalized Text Dad Hats for Men & Women Strap Closure |
| ✅ | public_0126 | 浏览型 | medium | B09M84R91V | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Asvivid Womens Casual Boho Floral Print 3/4 Flare Sleeve Blouses Summer Off The Shoulder Tops Tie Knot Shirts |
| ✅ | public_0127 | 浏览型 | medium | B0B8DX189T | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Under Armour Storm Fleece Gloves |
| ✅ | public_0128 | 浏览型 | medium | B0BNP1RZ2W | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | PAVOI 14K Gold Plated Lightweight Chunky Open Hoops \| Gold Hoop Earrings for Women |
| ✅ | public_0129 | 购买型 | easy | B0936ZJJ68 | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | MANGOPOP Women's Square Neck Short Sleeve Long Sleeve Tops Bodysuit Jumpsuit |
| ✅ | public_0130 | 意图覆写 | hard | B07X9V6HZX | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | POKARLA Women's High Waisted Cotton Underwear Soft Breathable Panties Stretch Briefs Regular & Plus Size 5-Pack |
| ✅ | public_0131 | 边界拒答 | medium | B07PQQQ8ZL | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Women Thigh High Socks Extra Long Cotton Knit Warm Thick Tall Long Boot Stockings Leg Warmers |
| ✅ | public_0132 | 购买型 | easy | B08X2X83DW | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | isotoner Women's Terry Slip on Clog Slipper with Memory Foam for Indoor/Outdoor Comfort |
| ✅ | public_0133 | 购买型 | easy | B01KILT64Q | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Flying Fisherman womens 7719cs sunglasses, Camo Frames/Smoke Lenses, Medium US |
| ✅ | public_0134 | 浏览型 | medium | B081SF3QRL | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | YOFANST 2pcs-12pcs Double Flare Stainless Steel Tunnels Gauges Screwed Gem Rhinestones Tunnels Plugs Stretcher Jewelry |
| ✅ | public_0135 | 购买型 | easy | B0C6BL4RNN | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Dearfoams Women's Rebecca Lightweight Cozy Memory Foam Closed Back Slipper with Wide Widths |
| ✅ | public_0136 | 购买型 | easy | B091F54MWM | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | CAMPSNAIL 4 Pack Biker Shorts for Women High Waist - 5" Soft Summer Womens Shorts Spandex Workout Shorts for Running Athletic |
| ✅ | public_0137 | 浏览型 | medium | B01N67CJGX | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | DOUBLJU Lightweight Thin Zip-Up Hoodie Jacket for Women Girls Kids with Plus Size |
| ✅ | public_0138 | 浏览型 | medium | B0B4BRW7JT | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | KORSIS Summer Dresses For Women Casual T Shirt Dresses Swing Flowy Beach Vacation Sundress with Pockets |
| ✅ | public_0139 | 浏览型 | medium | B09SGYPW3M | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | OFEEFAN Womens Tops Ruffle Short Sleeve V Neck T-Shirts Casual Loose Fit |
| ✅ | public_0140 | 浏览型 | medium | B09BT6LSJV | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Grlasen Women's Casual Long Blazers Ruched 3/4 Sleeve Lapel Oversized Suit Jacket Elegant Work Office Blazer Jackets |
| ✅ | public_0141 | 浏览型 | medium | B0BLH7JHG8 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Fzroezz 6Pcs Nose Studs L Shaped 20 Gauge Nose Piercings Nose Rings Studs Nose Piercing Jewelry Nose Piercing Stud Surgical Steel Nose Ring Nose Rings Studs Jewelry for Women Men 20G 2mm 2.5mm 3mm CZ Gold Silver Rose Gold |
| ✅ | public_0142 | 意图覆写 | hard | B07YRGC1Q1 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Feraco Mens Bikers Bracelet Stainless Steel Motorcycle Bike Chain Bracelets 8.4 Inch |
| ✅ | public_0143 | 购买型 | easy | B01H54X6CM | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | MUXXN Women's Retro 1950s Style Sleeveless Slim Business Pencil Dress |
| ✅ | public_0144 | 意图覆写 | hard | B08LMMDYV7 | 4 | 1 | 1 | 0.70 | **0.940** | 0.790 | +0.150 | URBAN REPUBLIC Women's Winter Jacket - Heavyweight Water Resistant Expedition Faux-Fur Lined Parka Jacket |
| ✅ | public_0145 | 购买型 | easy | B00IJZZWGA | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | BRIGHT STAR Low Cut Ankle Socks For Women - 30 Pairs of Athletic Socks For Running, Workout, Sports |
| ✅ | public_0146 | 购买型 | easy | B0BCQWYQLQ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Sarin Mathews Womens One Shoulder Ruched Bodycon Dress Sexy Sleeveless Slit Midi Party Cocktail Wedding Guest Dresses |
| ✅ | public_0147 | 浏览型 | medium | B077276QGC | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | wirarpa Women's High Waisted Cotton Underwear Ladies Soft Full Briefs Panties Multipack |
| ✅ | public_0148 | 购买型 | easy | B0BQC2NRG2 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Fruit of the Loom Women's Eversoft Cotton Bikini Underwear, Tag Free & Breathable |
| ✅ | public_0149 | 购买型 | easy | B07CBYYHTL | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | SDIYABOLO Small Black Sling Crossbody Backpack Shoulder Bag for Men Women Vintage PU Leather Sling Backpack Cycling |
| ✅ | public_0150 | 浏览型 | medium | B07P6MPQY5 | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Sivvan Scrubs for Men - Zippered Short Sleeve Jacket |
| ✅ | public_0151 | 浏览型 | medium | B08CFNQNJK | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Under Armour Men's Micro G Valsetz Mid Military and Tactical Boot |
| ✅ | public_0152 | 购买型 | easy | B000EQU0NW | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Citizen Eco-Drive Corso Quartz Mens Watch, Stainless Steel with Leather strap, Classic, Brown (Model: BM8242-08E) |
| ✅ | public_0153 | 浏览型 | medium | B07BMJ77FR | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Susanny High Heel Boots for Women,Womens Platform Boot Heels Sexy Round Toe Lace UP High Heels Mid Calf Boots |
| ✅ | public_0154 | 购买型 | easy | B00CYNKSTE | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Bestform Women's Wire Free Bra |
| ✅ | public_0155 | 购买型 | easy | B0C4VLWWYY | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | GearTOP Net Hat UV Protection Sun Hat Head Net Hat Fishing Hat for Men & Women Wide Brim Hat w/Removable Net |
| ✅ | public_0156 | 购买型 | easy | B0C3KZXV4B | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | adidas Alliance II Sackpack, Shadow Navy/Snowglobe/Dash Grey, One Size |
| ✅ | public_0157 | 购买型 | easy | B00BCHDM14 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Kamik Women's Momentum Snow Boot |
| ✅ | public_0158 | 浏览型 | medium | B012ZM6RGQ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | CreepyParty Novelty Halloween Costume Party Animal Head Mask - King Lion |
| ✅ | public_0159 | 购买型 | easy | B00UHLFR32 | 2 | 1 | 1 | 0.90 | **0.980** | 0.960 | +0.020 | Fruit of the Loom Men's Extended Sizes Jersey Knit Sleep Pant (1 & 2 Packs) |
| ✅ | public_0160 | 购买型 | easy | B01AAANF2Y | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Amazon Basics 4 Piece Packing Travel Organizer Cubes Set - Slim, Black |
| 🔴 | public_0161 | 购买型 | easy | B0B6N6TJ6V | 3 | 2 | 1 | 0.80 | **0.810** | 0.810 | +0.000 | Thankful Grateful Blessed Shirt for Women Plaid Pumpkin Long Sleeve Tshirts Leopard Stripe Striped Thanksgiving Fall Tee Tops |
| ✅ | public_0162 | 浏览型 | medium | B0B71JNMQY | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Satin Silk Slip Maxi Dress for Wedding Guest Women- Cowl Neck Pleated Bust Split Wedding Guest Cocktail Midi Dresses |
| ✅ | public_0163 | 购买型 | easy | B0834T68X3 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | DOUSSPRT Womens Walking Shoes Slip on Sock Sneakers Lady Girls Nurse Mesh Air Cushion Platform Loafers Fashion Casual |
| ✅ | public_0164 | 浏览型 | medium | B0C61FG7GL | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | BARTON Elite Silicone Watch Bands - Quick Release - Choose Strap Color & Buckle Color (Stainless Steel, Black PVD or Gunmetal Grey) - (ODD SIZE LUG WIDTHS ONLY 19mm, 21mm, 23mm - MOST WATCHES HAVE EVEN SIZED LUG WIDTHS, PLEASE MEASURE CAREFULLY) |
| ✅ | public_0165 | 购买型 | easy | B09XHSLX4X | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | WOCCI Leather Watch Band, Vintage Replacement Strap, Stainless Steel Buckle, Choice of Width 14mm 16mm 18mm 19mm 20mm 21mm 22mm 23mm 24mm |
| ✅ | public_0166 | 意图覆写 | hard | B00IHW88W0 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Muck Boots Hale Multi-Season Women's Rubber Boot |
| ✅ | public_0167 | 浏览型 | medium | B07357B79L | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Champion Women's Absolute Sports Bra with SmoothTec Band, Graphic |
| ✅ | public_0168 | 购买型 | easy | B08YYHDJD1 | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | Desimtion Mothers Day Gifts,Mother Daughter Bracelets Set for 2,3,4,5,6.Matching Heart Back to School Bracelets for Mommy and Me Easter Gifts for Girl |
| ✅ | public_0169 | 边界拒答 | medium | B0829R9M5G | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Amazon Essentials Women's Pull-On Knit Jegging (Available in Plus Size) |
| ✅ | public_0170 | 浏览型 | medium | B08LRQX5RH | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | UGG Women's Harrison Lace Fashion Boot |
| ✅ | public_0171 | 购买型 | easy | B0BFVFFHKS | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | ZAFUL Bikini Set for Women Solid V Neck Knot Front Push Up High Leg Thong Two Piece Swimsuit |
| 🔴 | public_0172 | 浏览型 | medium | B0829PZGBB | 3 | 2 | 1 | 0.80 | **0.810** | 0.810 | +0.000 | Skechers Women's Sneaker |
| ✅ | public_0173 | 浏览型 | medium | B07THT4G8N | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Aqua Socks Beach Water Shoes Barefoot Yoga Socks Quick-Dry Surf Pool Swim Shoes for Women Men |
| ✅ | public_0174 | 购买型 | easy | B0794VPVBH | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | NY Threads Luxurious Mens Shawl Collar Fleece Bathrobe Spa Robe |
| 🔴 | public_0175 | 浏览型 | medium | B07D5M61T2 | 3 | 2 | 1 | 0.80 | **0.810** | 0.810 | +0.000 | Ariat Men’s M2 Relaxed Boot Cut Jean |
| ✅ | public_0176 | 浏览型 | medium | B0C3MKNZJN | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | adidas Originals Originals Sport Waist Pack |
| ✅ | public_0177 | 意图覆写 | hard | B07HV9WW6Q | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | ANIXAY Women's Short/Long Sleeve Henley Button up T Shirt Casual Basic Tops Blouse |
| ✅ | public_0178 | 购买型 | easy | B01FWQ8NH8 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Red Hot Chili Peppers Distressed Men's T-Shirt Black |
| ✅ | public_0179 | 购买型 | easy | B08JK818ZD | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Azules Women's Long Sleeve Flowy Tunic |
| ✅ | public_0180 | 边界拒答 | medium | B01HSMYV8E | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Saucony Women's Cohesion 10 Running Shoe |
| ✅ | public_0181 | 浏览型 | medium | B08M3WKDFJ | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Fixmatti Women's 2 Piece Outfits Long Sleeve Pullover Sweatshirt Jogger Pants Sweatsuit |
| ✅ | public_0182 | 浏览型 | medium | B0C5XBLB2P | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | ELFISH Mini RFID Aluminum Wallet Credit Cards Holder Business Card Case Metal ID Case for Men Women (Black Marble) |
| ✅ | public_0183 | 意图覆写 | hard | B07Z2KSZR3 | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | SheIn Women's Double Breasted Long Vest Jacket Casual Sleeveless Pocket Outerwear Longline |
| ✅ | public_0184 | 浏览型 | medium | B0BWLFCTTF | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Ray-Ban Woman Sunglasses Black Frame, Green Classic G-15 Lenses, 57MM |
| ✅ | public_0185 | 购买型 | easy | B0BCW4QKV5 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | MIOTAN Boy Shorts Underwear for Women High Waisted Panties Cotton Boxer Briefs 4 Pack |
| ✅ | public_0186 | 意图覆写 | hard | B07XPLHXC1 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | ASICS Women's Gel-Contend 6 Running Shoes |
| ✅ | public_0187 | 边界拒答 | medium | B000GQ1F3O | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Eastland Men's Newport Slip-On Shoe |
| ✅ | public_0188 | 购买型 | easy | B0B5ZS2J2W | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | CLUCI Crossbody Purses for Women, Medium Size Zipper Pocket Adjustable Strap, Soft Leather Women's Shoulder Handbags |
| ✅ | public_0189 | 购买型 | easy | B0C614ZPK3 | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Levi's Men's 505 Regular Fit Shorts (Also Available in Big & Tall) |
| ✅ | public_0190 | 购买型 | easy | B01MQUDPPO | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Iflex Scrubs for Women, Yoga-Inspired Knit Waistband Scrub Pants CK002 |
| ✅ | public_0191 | 浏览型 | medium | B083TB1NDK | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | CS CELERSPORT 3 Pairs Compression Socks for Men and Women 20-30 mmHg Running Support Socks |
| ✅ | public_0192 | 边界拒答 | medium | B0C62MF2HV | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | adidas unisex adult Adilette Clog Slide Sandal, Pink Tint/White/Pink Tint, 12 Women Men US |
| ✅ | public_0193 | 购买型 | easy | B07YM55NLW | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | Shimmer Anna Shine USA American Flag Patriotic Scarf |
| ✅ | public_0194 | 购买型 | easy | B09WR1NZ48 | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Graphic Tees for Women Short Sleeve Tshirts,Womens Summer Tops Crewneck Shirt Blouse |
| ✅ | public_0195 | 浏览型 | medium | B072M4K5LF | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Floerns Women's Ruffle Off Shoulder Rose Embroidery Loose Blouse Top |
| ✅ | public_0196 | 浏览型 | medium | B073T364MM | 2 | 1 | 1 | 0.90 | **0.980** | 0.980 | +0.000 | DREAM PAIRS Women's Sole-Simple Ballerina Walking Flats Shoes |
| ✅ | public_0197 | 意图覆写 | hard | B07FDNP55K | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | Watch Band Strap Link Pins Remover Repair Tool,24 in 1 Kit with 6 Extra Tips Replacement,20PCS Cotter Pin,Spring Bar Tool Set,1PCS Head Hammer |
| ✅ | public_0198 | 意图覆写 | hard | B08K1ZJZ4N | 4 | 1 | 1 | 0.70 | **0.940** | 0.940 | +0.000 | lola mae Quilted Crossbody Bag, Medium Lightweight Shoulder Purse Top Zipper Tassel Accent |
| ✅ | public_0199 | 购买型 | easy | B089M57PSQ | 3 | 1 | 1 | 0.80 | **0.960** | 0.960 | +0.000 | Boboking 100% Cotton Little Boys Briefs Soft Dinosaur Truck Toddler Underwear |
| ✅ | public_0200 | 购买型 | easy | B07VFZ2FC2 | 1 | 1 | 1 | 1.00 | **1.000** | 1.000 | +0.000 | FUNKYMONKEY Mens Bathroom Shower Slippers Indoor Home Beach Non Slip Sandal |

## 9. 测试范围说明

本报告纳入所有正式测试/评测入口：官方端到端评测、模板改写鲁棒性、契约与对抗输入、评测器单元测试、冷启动和延迟基准。
`sweep_weights.py`（权重扫描）与 `probe_selectivity.py`（信号可辨识性分析）属于调研/调参工具，不是 pass/fail 测试，也不计入正式总分。
