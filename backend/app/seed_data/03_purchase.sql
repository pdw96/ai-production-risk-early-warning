-- 구매 기준정보 — 공급사별 품목.
--
-- 01_common_codes.sql 의 거래처와 품목 표의 행을 **코드로 찾아** 잇는다. id 를
-- 직접 적지 않는 이유는 id 가 시드 순서에 딸린 값이라, 품목 하나를 앞에 끼워
-- 넣으면 이 파일의 모든 줄이 조용히 다른 자재를 가리키게 되기 때문이다.
--
-- 리드타임은 **시간**으로 적는다(지적 ⑬). 공급사가 말하는 「3일」은 3 × 24 = 72
-- 이며, 그 곱을 여기 경계에서 한 번만 한다. 저장된 숫자 하나만 보고는 그것이
-- 날인지 시간인지 알 수 없으므로 단위를 섞지 않는다.
--
-- 환산 계수는 「구매 단위 하나가 재고 단위로 얼마인가」다. 25kg 포대로 사는
-- 자재는 구매 단위 kg 에 계수 25 가 아니라, 재고 단위와 구매 단위가 같으면
-- 계수 1 이다 — 포대라는 단위를 UOM 에 넣기 전까지는 그렇다.

INSERT INTO supplier_items
  (partner_id, item_id, lead_time_hours, purchase_uom_group, purchase_uom, conversion_factor)
SELECT
  partners.id,
  items.id,
  source.lead_time_days * 24,
  'UOM',
  items.stock_uom,
  1.0
FROM (
  -- 공급사는 무리를 나눠 맡는다. 분체는 한빛소재, 액상·수지는 대원케미컬,
  -- 시트·필름은 정우필름이다.
  SELECT 'SUP-02' AS partner_code, 'RM-01' AS item_code, 5  AS lead_time_days
  UNION ALL SELECT 'SUP-01', 'RM-02', 7
  UNION ALL SELECT 'SUP-01', 'RM-03', 10
  UNION ALL SELECT 'SUP-03', 'RM-04', 14
  UNION ALL SELECT 'SUP-02', 'RM-05', 5
  UNION ALL SELECT 'SUP-01', 'RM-06', 7
  UNION ALL SELECT 'SUP-03', 'RM-07', 12
  UNION ALL SELECT 'SUP-02', 'RM-08', 6
  UNION ALL SELECT 'SUP-01', 'RM-09', 7
  UNION ALL SELECT 'SUP-02', 'RM-10', 5
  UNION ALL SELECT 'SUP-03', 'RM-11', 9
  UNION ALL SELECT 'SUP-02', 'RM-12', 8
  UNION ALL SELECT 'SUP-02', 'RM-13', 21
  UNION ALL SELECT 'SUP-01', 'RM-14', 10
  UNION ALL SELECT 'SUP-03', 'RM-15', 6
) AS source
JOIN partners ON partners.code = source.partner_code
JOIN items ON items.code = source.item_code;
