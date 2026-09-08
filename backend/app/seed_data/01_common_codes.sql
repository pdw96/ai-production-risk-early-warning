-- 기준정보. 사람이 읽고 고치는 표다.
--
-- 여기에 「오늘」이 나오지 않는다는 것이 이 파일과 파이썬 시드를 가르는 경계다.
-- 기준정보는 날짜를 모르고, 시나리오는 기준일 없이는 존재할 수 없다. 그래서
-- 로트 · 예정 입고 · 생산 실적 · 검사 기록은 여기 없다 — 고정 INSERT 로 적으면
-- 내일 낡기 때문이다.
--
-- 코드를 몰라도 고칠 수 있는 것이 이 파일의 가장 큰 이득이다. 품목 하나 추가가
-- 한 줄 추가이고, 새 불합격 사유 하나가 한 줄 추가다.


-- ════════════════════════════════════════════════════════════════════════
-- 공통코드 그룹
--
-- 그룹은 전부 Major다 — 프로그램이 이름으로 부르므로 화면에서 늘거나 줄지
-- 않는다. `value_fixed` 가 참이면 값마다 프로그램이 다른 일을 하고, 거짓이면
-- 세기만 하므로 얼마든지 늘어도 아무것도 고장 나지 않는다.
-- ════════════════════════════════════════════════════════════════════════
INSERT INTO code_groups (group_code, name, value_fixed, description) VALUES
  ('WAREHOUSE',  '창고',         TRUE, '흐름의 구간이다. 창고를 더하면 도해가 바뀐다.'),
  ('STOCK_TYPE', '재고구분',     TRUE, '출하 가능 여부를 가른다.'),
  ('ITEM_TYPE',  '품목유형',     TRUE, 'BOM 전개와 검사 경로가 갈린다.'),
  ('TXN_TYPE',   '수불유형',     TRUE, '부호와 재고 반영이 유형마다 다르다.'),
  ('INSP_STAGE', '검사단계',     TRUE, '단계마다 다른 일을 한다.'),
  ('ORDER_TYPE', '오더유형',     TRUE, '2단 BOM 전개의 두 자리.'),
  ('ORDER_MODE', '오더성격',     TRUE, '양산과 시양산은 오더유형과 다른 축이다.'),
  ('SHIP_TYPE',  '출하유형',     TRUE, '보이는 재고가 갈린다.'),
  ('ITEM_PHASE', '품목단계',     TRUE, '게이트와 지표가 다르다(Ppk 1.67 / Cpk 1.33).'),
  ('MEAS_KIND',  '항목유형',     TRUE, '계량만 관리도에 오른다.'),
  ('SIGMA_SRC',  'σ출처',        TRUE, 'Cpk 를 낼지 말지를 정한다 — 「미정」이면 숫자를 내지 않는다.'),
  ('WE_RULE',    '판정규칙',     TRUE, '규칙마다 계산이 다르고, 검사 기준에서 켜고 끄는 단위다.'),
  ('SHIFT',      '근무형태',     TRUE, '실사 창과 경과 시간 계산이 여기서 나온다.'),
  ('SETTLE_TYPE','반품정산',     TRUE, '대물은 물건이 돌아가고 대금은 전산상 소멸한다.'),
  ('RISK_STATUS','경보상태',     TRUE, 'risk_statuses.status 로 이미 코드에 있다.'),
  ('NC_REASON',  '불합격사유',   FALSE, '계량 14는 검사 항목에서 따라 나오고 손으로 두는 것은 계수 4뿐이다.'),
  ('PO_CLOSE',   '미납종결사유', FALSE, '누구 탓인가와 그 물건이 아직 필요한가를 센다.'),
  ('SP_REASON',  '특채사유',     FALSE, '불합격인데 쓰기로 한 결정의 이유.'),
  ('ADJ_REASON', '조정사유',     FALSE, '실제로 조정을 내 보아야 목록이 나온다 — 지금은 비어 있는 것이 맞다.'),
  ('PROCESS',    '공정',         FALSE, '검사 항목을 고르는 라벨이다. 설비와 라우팅이 들어오면 고정 쪽으로 옮겨간다.'),
  ('INSP_ITEM',  '검사항목',     FALSE, '이름만 여기 있고 규격·중심선·경고선·σ·경시변화는 (공정 × 항목) 표에 있다.'),
  ('DEPT',       '부서',         FALSE, '조직의 사실. 교차 실사 기록이 이것을 요구한다.'),
  ('UOM',        '단위',         FALSE, 'kg · L · EA · m² — 늘어도 아무것도 고장 나지 않는다.');


-- ════════════════════════════════════════════════════════════════════════
-- 값이 고정된 그룹
-- ════════════════════════════════════════════════════════════════════════

-- 창고 셋. 담는 것이 정해져 있다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('WAREHOUSE', '원재료창고', '원재료창고', '입고된 자재를 보관한다.', 1, TRUE),
  ('WAREHOUSE', '생산창고',   '생산창고',   '원재료창고에서 이동한 자재와, 검사 대기·불합격·이송 대기 완제품이 있다.', 2, TRUE),
  ('WAREHOUSE', '제품창고',   '제품창고',   '출하검사에 합격한 완제품만 적재된다.', 3, TRUE);

INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('STOCK_TYPE', '양품',   '양품',   '출하 가능 재고로 센다.', 1, TRUE),
  ('STOCK_TYPE', '불량품', '불량품', '총량에는 남고 출하 가능 재고에서는 빠진다.', 2, TRUE);

INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('ITEM_TYPE', '완제품', '완제품', '출하되는 것. 유효기간을 갖는다.', 1, TRUE),
  ('ITEM_TYPE', '반제품', '반제품', '만들어지면서 쓰인다. 유효기간을 두지 않는다.', 2, TRUE),
  ('ITEM_TYPE', '원자재', '원자재', '구매해 들어오는 것.', 3, TRUE);

-- 수불유형 열둘. 아무도 고르지 않는다 — 어느 화면에서 일어났는가가 정한다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('TXN_TYPE', '전기이월',      '전기이월',      '월말 마감이 낳는다. 잔량은 이 줄부터 더한다.', 1, TRUE),
  ('TXN_TYPE', '구매입고',      '구매입고',      'IQC 합격·특채 승인에서 로트가 처음 생기는 자리.', 2, TRUE),
  ('TXN_TYPE', '구매반품출고',  '구매반품출고',  '구매반품관리의 대물정산.', 3, TRUE),
  ('TXN_TYPE', '생산출고',      '생산출고',      '자재 불출. 창고를 건너므로 짝이 함께 난다.', 4, TRUE),
  ('TXN_TYPE', '생산입고',      '생산입고',      '자재가 투입 대기로 들어온다.', 5, TRUE),
  ('TXN_TYPE', '생산소모',      '생산소모',      '자재·반제품이 사라진다. 없으면 불출받은 자재가 영원히 쌓인다.', 6, TRUE),
  ('TXN_TYPE', '생산산출',      '생산산출',      '반제품·완제품 로트가 생긴다.', 7, TRUE),
  ('TXN_TYPE', '제품입고',      '제품입고',      '완제품 로트가 제품창고로 들어온다.', 8, TRUE),
  ('TXN_TYPE', '판매출고',      '판매출고',      '출하 실적. 여기서 재고가 준다.', 9, TRUE),
  ('TXN_TYPE', '재고구분대체',  '재고구분대체',  '양불이동. 총량은 그대로이나 양품재고는 준다.', 10, TRUE),
  ('TXN_TYPE', '조정',          '조정',          '재고조정 승인 후. 유일하게 사람이 사유를 넣는 유형이다.', 11, TRUE),
  ('TXN_TYPE', '폐기출고',      '폐기출고',      '재작업 불가분과 OQC 불합격분.', 12, TRUE);

INSERT INTO txn_type_attributes (group_code, code, total_effect, paired_code, source_document_type) VALUES
  ('TXN_TYPE', '전기이월',     '기준점', NULL,           '월말 마감'),
  ('TXN_TYPE', '구매입고',     '증가',   NULL,           'IQC 판정'),
  ('TXN_TYPE', '구매반품출고', '감소',   NULL,           '구매반품관리'),
  ('TXN_TYPE', '생산출고',     '감소',   '생산입고',     '재고이동 처리'),
  ('TXN_TYPE', '생산입고',     '증가',   '생산출고',     '재고이동 처리'),
  ('TXN_TYPE', '생산소모',     '감소',   '생산산출',     'IPQC·FQC 판정'),
  ('TXN_TYPE', '생산산출',     '증가',   '생산소모',     'IPQC·FQC 판정'),
  ('TXN_TYPE', '제품입고',     '증가',   NULL,           '재고이동 처리'),
  ('TXN_TYPE', '판매출고',     '감소',   NULL,           '출하 실적'),
  ('TXN_TYPE', '재고구분대체', '불변',   NULL,           '양불이동'),
  ('TXN_TYPE', '조정',         '양방향', NULL,           '재고조정'),
  ('TXN_TYPE', '폐기출고',     '감소',   NULL,           '폐기');

-- 검사단계 다섯. IQC 는 자재 로트를 만들고 FQC 는 완제품 로트를 만든다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('INSP_STAGE', 'IQC',    '수입검사',   '자재 로트를 만든다.', 1, TRUE),
  ('INSP_STAGE', 'IPQC',   '공정검사',   '반제품 배치를 본다.', 2, TRUE),
  ('INSP_STAGE', 'FQC',    '최종검사',   '완제품 로트를 만든다.', 3, TRUE),
  ('INSP_STAGE', 'OQC',    '출하검사',   '출하 로트를 본다.', 4, TRUE),
  ('INSP_STAGE', 'RETEST', '재검사',     '만료 로트가 돌아오는 자리. 경시 변화 항목만 다시 본다.', 5, TRUE);

INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('ORDER_TYPE', '제품',   '제품오더',   '2단 BOM 의 1단.', 1, TRUE),
  ('ORDER_TYPE', '반제품', '반제품오더', '2단 BOM 의 2단.', 2, TRUE),
  ('ORDER_MODE', '양산',   '양산',       'Cpk 1.33 이 상시 지표다.', 1, TRUE),
  ('ORDER_MODE', '시양산', '시양산',     'Ppk 1.67 로 전환을 판정한다.', 2, TRUE),
  ('SHIP_TYPE',  '정상',   '정상 출하',  '양품재고에서 나간다.', 1, TRUE),
  ('SHIP_TYPE',  '등급하향','등급 하향 판매', '불량품재고에서 나간다. 단가는 건별 협상이라 수주의 칸이다.', 2, TRUE),
  ('ITEM_PHASE', '초기',   '초기',       '초기 공정 조사 구간. Ppk 1.67 로 게이트를 통과한다.', 1, TRUE),
  ('ITEM_PHASE', '양산',   '양산',       'Cpk 1.33 을 상시로 본다.', 2, TRUE),
  ('MEAS_KIND',  '계량',   '계량',       '재는 것. 관리도에 오른다.', 1, TRUE),
  ('MEAS_KIND',  '계수',   '계수',       '세는 것. 관리한계가 없고 불량률 집계로 본다.', 2, TRUE),
  ('SETTLE_TYPE','대물',   '대물정산',   '물건이 공급사로 돌아간다.', 1, TRUE),
  ('SETTLE_TYPE','대금',   '대금정산',   '환불 후 전산상 소멸한다.', 2, TRUE);

-- σ 출처. 이 칸이 없으면 화면의 Cpk 가 진짜인지 자리표시자인지 아무도 모른다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('SIGMA_SRC', '미정', '미정', '규격·경고선·중심선만 그린다. Cpk 는 숫자를 내지 않는다.', 1, TRUE),
  ('SIGMA_SRC', '임의', '임의', '목표 Cpk 에서 역산한 σ. 관리한계와 규칙 1·4 는 돌고 규칙 2·3 은 꺼져 있다.', 2, TRUE),
  ('SIGMA_SRC', '실측', '실측', '부분군 25군 이상에서 나온 σ. Cpk 가 비로소 공정에 대한 진술이 된다.', 3, TRUE);

-- 웨스턴 일렉트릭 규칙 넷. 넷 중 셋이 「연속」을 세므로 점의 순서를 요구한다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('WE_RULE', 'WE1', '1점이 3σ 밖',              '갑작스러운 이상. 점 하나면 되고 순서가 필요 없다.', 1, TRUE),
  ('WE_RULE', 'WE2', '연속 3점 중 2점이 2σ 밖',  '치우침. 점의 순서와 σ 가 필요하다.', 2, TRUE),
  ('WE_RULE', 'WE3', '연속 5점 중 4점이 1σ 밖',  '치우침. 점의 순서와 σ 가 필요하다.', 3, TRUE),
  ('WE_RULE', 'WE4', '연속 8점이 중심선 같은 쪽', '중심이 이동함. 중심선 하나면 판정되므로 σ 가 없어도 돈다.', 4, TRUE);

-- 근무형태 셋. 현장은 12시간씩 2교대이고 빈칸이 없다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('SHIFT', 'DAY',    '현장 주간', '09:00–21:00', 1, TRUE),
  ('SHIFT', 'NIGHT',  '현장 야간', '21:00–09:00. 자정을 넘으므로 한 조가 두 날짜에 걸친다.', 2, TRUE),
  ('SHIFT', 'OFFICE', '사무',      '08:30–17:30. 승인과 결정이 이 창에서만 일어난다.', 3, TRUE);

INSERT INTO shift_patterns (group_code, code, starts_at, ends_at, on_site) VALUES
  ('SHIFT', 'DAY',    '09:00:00', '21:00:00', TRUE),
  ('SHIFT', 'NIGHT',  '21:00:00', '09:00:00', TRUE),
  ('SHIFT', 'OFFICE', '08:30:00', '17:30:00', FALSE);

-- 경보상태. 이미 risk_statuses.status 로 코드에 있는 값 셋을 그대로 적는다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('RISK_STATUS', '신규',      '신규',      '아직 아무도 보지 않았다.', 1, TRUE),
  ('RISK_STATUS', '확인 중',   '확인 중',   '담당자가 들여다보고 있다.', 2, TRUE),
  ('RISK_STATUS', '조치 완료', '조치 완료', '권장 조치를 마쳤다.', 3, TRUE);


-- ════════════════════════════════════════════════════════════════════════
-- 값이 늘 수 있는 그룹
-- ════════════════════════════════════════════════════════════════════════

-- 단위. 재고 단위는 품목에 못박히고 모든 수량이 그것으로 저장된다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('UOM', 'EA', '개',      '낱개로 세는 것.', 1, TRUE),
  ('UOM', 'kg', '킬로그램','분체는 세는 것이 아니라 다는 것이다.', 2, TRUE),
  ('UOM', 'L',  '리터',    '액상·수지.', 3, TRUE),
  ('UOM', 'm2', '제곱미터','시트·필름은 넓이로 잰다.', 4, TRUE);

-- 공정 다섯. 여기서 공정은 검사 항목을 고르는 라벨이며 설비도 라우팅도 아니다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('PROCESS', '수입',     '수입',      'RM- 를 받는다. IQC.', 1, TRUE),
  ('PROCESS', '배합',     '배합',      'RM- 에서 SF- 로. IPQC.', 2, TRUE),
  ('PROCESS', '코팅',     '코팅',      'SF- 를 다룬다. IPQC.', 3, TRUE),
  ('PROCESS', '적층경화', '적층·경화', 'SF- 에서 FG- 로. FQC.', 4, TRUE),
  ('PROCESS', '출하',     '출하',      'FG- 를 내보낸다. OQC.', 5, TRUE);

-- 검사항목 열여덟 — 계량 열넷 · 계수 넷. 이름만 여기 있고 규격은 (공정 × 항목)에 있다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('INSP_ITEM', 'IT-PSD', '입도',      '분체의 입자 크기.', 1, TRUE),
  ('INSP_ITEM', 'IT-MOI', '수분',      '분체의 함수율.', 2, TRUE),
  ('INSP_ITEM', 'IT-VIS', '점도',      '액상·수지의 흐름.', 3, TRUE),
  ('INSP_ITEM', 'IT-THK', '두께',      '시트·필름과 완제품의 두께.', 4, TRUE),
  ('INSP_ITEM', 'IT-WID', '폭',        '시트·필름의 폭.', 5, TRUE),
  ('INSP_ITEM', 'IT-DIM', '치수',      '수입 자재의 치수 일반.', 6, TRUE),
  ('INSP_ITEM', 'IT-COL', '색차',      'ΔE.', 7, TRUE),
  ('INSP_ITEM', 'IT-TMP', '공정 온도', '배합 공정의 조건.', 8, TRUE),
  ('INSP_ITEM', 'IT-MVS', '혼합 점도', '배합 후의 점도.', 9, TRUE),
  ('INSP_ITEM', 'IT-MIX', '배합비',    '물건 자체가 틀어지는 자리 — 되돌릴 수 없다.', 10, TRUE),
  ('INSP_ITEM', 'IT-CTH', '도포 두께', '코팅 공정의 조건.', 11, TRUE),
  ('INSP_ITEM', 'IT-SPD', '라인 속도', '코팅 공정의 조건.', 12, TRUE),
  ('INSP_ITEM', 'IT-GLS', '광택',      '표면 광택.', 13, TRUE),
  ('INSP_ITEM', 'IT-ADH', '접착력',    '고칠 수 없는 항목.', 14, TRUE),
  ('INSP_ITEM', 'IT-FM',  '이물',      '계수. 육안·여과 잔사.', 15, TRUE),
  ('INSP_ITEM', 'IT-PKG', '포장',      '계수. 계수·육안.', 16, TRUE),
  ('INSP_ITEM', 'IT-DOC', '성적서',    '계수. 문서 확인.', 17, TRUE),
  ('INSP_ITEM', 'IT-VFM', '외관 이물', '계수. 완제품 외관.', 18, TRUE);

-- 불합격사유 열아홉. 시드에 이미 자유 텍스트로 박혀 있던 여섯을 그대로 두고
-- 열셋을 보탠 것이다. 접두가 검사 단계를 말한다(지적 ⑯).
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('NC_REASON', 'IQ-FM',  '이물 혼입',              '세 무리 전부. 육안·여과 잔사.', 1, TRUE),
  ('NC_REASON', 'IQ-DIM', '치수 이탈 (두께·폭)',    '시트·필름. 두께 게이지·폭 실측.', 2, TRUE),
  ('NC_REASON', 'IQ-VIS', '점도 이탈',              '액상·수지. 점도계.', 3, TRUE),
  ('NC_REASON', 'IQ-PSD', '입도 이탈',              '분체. 입도 분석.', 4, TRUE),
  ('NC_REASON', 'IQ-MOI', '수분 초과',              '분체. 수분계.', 5, TRUE),
  ('NC_REASON', 'IQ-COL', '색차 초과',              '광학 안료·기능성 염료. 색차계 ΔE.', 6, TRUE),
  ('NC_REASON', 'IQ-EXP', '잔여 유효기간 부족',     '시스템이 입고일에서 계산해 자동으로 단다.', 7, TRUE),
  ('NC_REASON', 'IQ-PKG', '포장·수량 이상',         '전 품목. 계수·육안.', 8, TRUE),
  ('NC_REASON', 'IQ-DOC', '시험성적서 미비',        '전 품목. 물건은 정상이다.', 9, TRUE),
  ('NC_REASON', 'IP-TMP', '공정 온도 이탈',         '물건이 아니라 조건이 틀렸다.', 10, TRUE),
  ('NC_REASON', 'IP-VIS', '혼합 점도 편차',         '조건.', 11, TRUE),
  ('NC_REASON', 'IP-SPD', '라인 속도 불안정',       '조건.', 12, TRUE),
  ('NC_REASON', 'IP-MIX', '배합비 오차',            '물건 자체 — 되돌릴 수 없다.', 13, TRUE),
  ('NC_REASON', 'IP-THK', '도포 두께 이탈',         '조건.', 14, TRUE),
  ('NC_REASON', 'FQ-THK', '두께 규격 이탈',         'FQC 에서는 재작업, OQC 에서는 등급 하향.', 15, TRUE),
  ('NC_REASON', 'FQ-GLS', '표면 광택 편차',         'FQC 에서는 재작업, OQC 에서는 등급 하향.', 16, TRUE),
  ('NC_REASON', 'FQ-FM',  '외관 이물 검출',         '고칠 수 없다.', 17, TRUE),
  ('NC_REASON', 'FQ-ADH', '접착력 미달',            '고칠 수 없다.', 18, TRUE),
  ('NC_REASON', 'FQ-COL', '색차 초과',              '쓸 수는 있다.', 19, TRUE);

-- 계량 열넷은 검사 항목을 가리킨다. 목록을 두 벌 두면 반드시 갈린다 —
-- 항목에 「접착력」을 넣고 코드에 FQ-ADH 를 안 넣으면 불합격을 적을 수가 없다.
INSERT INTO nonconformity_attributes
  (group_code, code, measure_kind, inspection_item_group, inspection_item_code) VALUES
  ('NC_REASON', 'IQ-FM',  '계수', 'INSP_ITEM', 'IT-FM'),
  ('NC_REASON', 'IQ-DIM', '계량', 'INSP_ITEM', 'IT-DIM'),
  ('NC_REASON', 'IQ-VIS', '계량', 'INSP_ITEM', 'IT-VIS'),
  ('NC_REASON', 'IQ-PSD', '계량', 'INSP_ITEM', 'IT-PSD'),
  ('NC_REASON', 'IQ-MOI', '계량', 'INSP_ITEM', 'IT-MOI'),
  ('NC_REASON', 'IQ-COL', '계량', 'INSP_ITEM', 'IT-COL'),
  ('NC_REASON', 'IQ-EXP', '계수', NULL,        NULL),
  ('NC_REASON', 'IQ-PKG', '계수', 'INSP_ITEM', 'IT-PKG'),
  ('NC_REASON', 'IQ-DOC', '계수', 'INSP_ITEM', 'IT-DOC'),
  ('NC_REASON', 'IP-TMP', '계량', 'INSP_ITEM', 'IT-TMP'),
  ('NC_REASON', 'IP-VIS', '계량', 'INSP_ITEM', 'IT-MVS'),
  ('NC_REASON', 'IP-SPD', '계량', 'INSP_ITEM', 'IT-SPD'),
  ('NC_REASON', 'IP-MIX', '계량', 'INSP_ITEM', 'IT-MIX'),
  ('NC_REASON', 'IP-THK', '계량', 'INSP_ITEM', 'IT-CTH'),
  ('NC_REASON', 'FQ-THK', '계량', 'INSP_ITEM', 'IT-THK'),
  ('NC_REASON', 'FQ-GLS', '계량', 'INSP_ITEM', 'IT-GLS'),
  ('NC_REASON', 'FQ-FM',  '계수', 'INSP_ITEM', 'IT-VFM'),
  ('NC_REASON', 'FQ-ADH', '계량', 'INSP_ITEM', 'IT-ADH'),
  ('NC_REASON', 'FQ-COL', '계량', 'INSP_ITEM', 'IT-COL');

-- 처분 기본값은 코드가 아니라 「코드 × 단계」에 붙는다. 줄이 있는 것 자체가
-- 「그 단계에서 쓸 수 있는 코드」라는 뜻이므로 별도의 「적용 단계」 칸이 없다.
INSERT INTO nonconformity_stage_rules
  (reason_group, reason_code, stage_group, stage_code, disposition, special_acceptance_allowed) VALUES
  ('NC_REASON', 'IQ-FM',  'INSP_STAGE', 'IQC',  '반품',     FALSE),
  ('NC_REASON', 'IQ-DIM', 'INSP_STAGE', 'IQC',  '반품',     FALSE),
  ('NC_REASON', 'IQ-VIS', 'INSP_STAGE', 'IQC',  '반품',     TRUE),
  ('NC_REASON', 'IQ-PSD', 'INSP_STAGE', 'IQC',  '반품',     FALSE),
  ('NC_REASON', 'IQ-MOI', 'INSP_STAGE', 'IQC',  '반품',     FALSE),
  ('NC_REASON', 'IQ-COL', 'INSP_STAGE', 'IQC',  '반품',     TRUE),
  ('NC_REASON', 'IQ-EXP', 'INSP_STAGE', 'IQC',  '반품',     FALSE),
  ('NC_REASON', 'IQ-PKG', 'INSP_STAGE', 'IQC',  '환불',     FALSE),
  ('NC_REASON', 'IQ-DOC', 'INSP_STAGE', 'IQC',  '반품',     TRUE),
  ('NC_REASON', 'IP-TMP', 'INSP_STAGE', 'IPQC', '재작업',   FALSE),
  ('NC_REASON', 'IP-VIS', 'INSP_STAGE', 'IPQC', '재작업',   FALSE),
  ('NC_REASON', 'IP-SPD', 'INSP_STAGE', 'IPQC', '재작업',   FALSE),
  ('NC_REASON', 'IP-MIX', 'INSP_STAGE', 'IPQC', '폐기',     FALSE),
  ('NC_REASON', 'IP-THK', 'INSP_STAGE', 'IPQC', '재작업',   FALSE),
  ('NC_REASON', 'FQ-THK', 'INSP_STAGE', 'FQC',  '재작업',   FALSE),
  ('NC_REASON', 'FQ-GLS', 'INSP_STAGE', 'FQC',  '재작업',   FALSE),
  ('NC_REASON', 'FQ-FM',  'INSP_STAGE', 'FQC',  '폐기',     FALSE),
  ('NC_REASON', 'FQ-ADH', 'INSP_STAGE', 'FQC',  '폐기',     FALSE),
  ('NC_REASON', 'FQ-COL', 'INSP_STAGE', 'FQC',  '재작업',   FALSE),
  ('NC_REASON', 'FQ-THK', 'INSP_STAGE', 'OQC',  '등급 하향', FALSE),
  ('NC_REASON', 'FQ-GLS', 'INSP_STAGE', 'OQC',  '등급 하향', FALSE),
  ('NC_REASON', 'FQ-FM',  'INSP_STAGE', 'OQC',  '폐기',     FALSE),
  ('NC_REASON', 'FQ-ADH', 'INSP_STAGE', 'OQC',  '폐기',     FALSE),
  ('NC_REASON', 'FQ-COL', 'INSP_STAGE', 'OQC',  '등급 하향', FALSE);

-- 미납 종결 사유 일곱. 셀 것은 둘이다 — 누구 탓인가와 그 물건이 아직 필요한가.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('PO_CLOSE', 'PO-SHT', '부분 납품 종결', '나머지를 안 보내기로 함.', 1, TRUE),
  ('PO_CLOSE', 'PO-DLY', '지연 포기',      '너무 늦어 기다릴 수 없음.', 2, TRUE),
  ('PO_CLOSE', 'PO-STK', '공급 불가',      '재고 소진·생산 중단·부도.', 3, TRUE),
  ('PO_CLOSE', 'PO-EOL', '단종',           '공급사 쪽이지만 공급사의 잘못이 아니다.', 4, TRUE),
  ('PO_CLOSE', 'PO-CHG', '소요량 감소',    '계획이 줄었다.', 5, TRUE),
  ('PO_CLOSE', 'PO-CAN', '생산계획·오더 취소', '자사 사유.', 6, TRUE),
  ('PO_CLOSE', 'PO-ERR', '발주 오류',      '수량·품목을 잘못 시켰다.', 7, TRUE);

INSERT INTO purchase_close_attributes
  (group_code, code, responsibility, scorecard_axis, reorder_default) VALUES
  ('PO_CLOSE', 'PO-SHT', '공급사', '수량 준수율', '필요'),
  ('PO_CLOSE', 'PO-DLY', '공급사', '납기 준수율', '필요'),
  ('PO_CLOSE', 'PO-STK', '공급사', '공급 가능성', '필요'),
  ('PO_CLOSE', 'PO-EOL', '공급사', NULL,          '필요'),
  ('PO_CLOSE', 'PO-CHG', '자사',   NULL,          '불필요'),
  ('PO_CLOSE', 'PO-CAN', '자사',   NULL,          '불필요'),
  ('PO_CLOSE', 'PO-ERR', '자사',   NULL,          '건별');

-- 특채 사유 다섯. 속성 표가 없는 것은 「향하는 부서」가 읽는 사람이 아는 것이지
-- 프로그램이 쓰는 값이 아니기 때문이다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('SP_REASON', 'SP-URG', '납기 급박',   '기다리면 오더가 밀린다. 리드타임이나 안전재고가 짧다는 뜻이다.', 1, TRUE),
  ('SP_REASON', 'SP-ALT', '대체 불가',   '이 자재 아니면 못 만든다. 단일 공급.', 2, TRUE),
  ('SP_REASON', 'SP-MIN', '이탈 경미',   '규격에서 조금 벗어났다. 규격이 실제보다 빡빡할 수 있다.', 3, TRUE),
  ('SP_REASON', 'SP-ABS', '후공정 흡수', '다음 공정이 그 편차를 먹는다. 규격의 근거가 약하다.', 4, TRUE),
  ('SP_REASON', 'SP-DOC', '문서만 미비', '물건은 정상이다. 위험이 없는 유일한 특채다.', 5, TRUE);

-- 부서. 도해가 구간마다 담당을 정해 둔 그대로다.
INSERT INTO common_codes (group_code, code, name, description, sort_order, is_active) VALUES
  ('DEPT', 'PUR', '구매관리', '입고·가입고와 구매반품.', 1, TRUE),
  ('DEPT', 'PRD', '생산관리', '생산계획·오더와 재고이동 요청.', 2, TRUE),
  ('DEPT', 'INV', '재고관리', '창고를 건너는 처리는 전부 여기서 한다.', 3, TRUE),
  ('DEPT', 'QUA', '품질관리', '검사 기준과 판정.', 4, TRUE),
  ('DEPT', 'SAL', '영업관리', '수주와 출하.', 5, TRUE),
  ('DEPT', 'SYS', '시스템관리', '공통코드처럼 주체로 자리를 정할 수 없는 것.', 6, TRUE);

-- 조정사유는 비어 있다. 실제로 조정을 내 보아야 목록이 나오기 때문이며,
-- 빈 기준정보를 미리 채우면 없는 것이 있는 것처럼 보인다.


-- ════════════════════════════════════════════════════════════════════════
-- 거래처. 합성 데이터 원칙에 따라 전부 가상 이름이다.
-- ════════════════════════════════════════════════════════════════════════
INSERT INTO partners (code, name, partner_type, is_active) VALUES
  ('SUP-01', '한빛소재',     '공급사', TRUE),
  ('SUP-02', '대원케미컬',   '공급사', TRUE),
  ('SUP-03', '정우필름',     '공급사', TRUE),
  ('CUS-01', '가온전자',     '고객사', TRUE),
  ('CUS-02', '누리디스플레이','고객사', TRUE);


-- ════════════════════════════════════════════════════════════════════════
-- 공정별 검사 기준.
--
-- 품목 코드를 고르면 그 품목의 공정이 나오고, 공정이 항목 목록을 부르고,
-- 항목을 고르면 여섯 값이 딸려 온다. 사람이 넣는 것은 그 뒤의 측정값 하나뿐이다.
--
-- σ 는 전부 비어 있고 출처는 「미정」이다. 규격에서 σ 를 뽑으면 Cpk 가 계수의
-- 역수로 못박혀 공정에 대해 아무 말도 하지 않기 때문이다. 없는 것을 없다고
-- 표시하는 편이 가짜 Cpk 보다 낫다 — 측정값이 쌓이면 실측으로 채운다.
--
-- 계수 항목은 규격 셋이 전부 비어 있다. 재는 것이 아니라 세는 것이라 관리한계가
-- 없고, 그쪽은 불량률 집계로 본다.
--
-- 경시 변화가 켜진 것은 셋뿐이다 — 점도 · 수분 · 접착력. 잣대는 하나이고
-- 「시간이 이 값을 바꿀 수 있는가」다. 두께는 시간이 지나도 두께다.
-- ════════════════════════════════════════════════════════════════════════
INSERT INTO process_inspection_standards
  (process_group, process_code, item_group, item_code,
   upper_spec_limit, lower_spec_limit, center_line,
   warning_ratio, sigma, sigma_source, time_variant, unit) VALUES
  -- 수입 · IQC
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-PSD',  45.0,   15.0,   30.0,   0.70, NULL, '미정', FALSE, 'um'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-MOI',   0.50,   0.05,   0.20,  0.70, NULL, '미정', TRUE, '%'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-VIS', 1600.0,  800.0, 1200.0,  0.70, NULL, '미정', TRUE, 'cP'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-THK',  105.0,   95.0,  100.0,  0.70, NULL, '미정', FALSE, 'um'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-WID', 1010.0,  990.0, 1000.0,  0.70, NULL, '미정', FALSE, 'mm'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-DIM',  105.0,   95.0,  100.0,  0.70, NULL, '미정', FALSE, 'mm'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-COL',    1.50,   0.0,    0.50, 0.70, NULL, '미정', FALSE, 'dE'),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-FM',   NULL,   NULL,   NULL,   0.70, NULL, '미정', FALSE, NULL),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-PKG',  NULL,   NULL,   NULL,   0.70, NULL, '미정', FALSE, NULL),
  ('PROCESS', '수입',     'INSP_ITEM', 'IT-DOC',  NULL,   NULL,   NULL,   0.70, NULL, '미정', FALSE, NULL),
  -- 배합 · IPQC
  ('PROCESS', '배합',     'INSP_ITEM', 'IT-TMP',  185.0,  175.0,  180.0,  0.70, NULL, '미정', FALSE, 'C'),
  ('PROCESS', '배합',     'INSP_ITEM', 'IT-MVS', 2600.0, 2200.0, 2400.0,  0.70, NULL, '미정', TRUE, 'cP'),
  ('PROCESS', '배합',     'INSP_ITEM', 'IT-MIX',  100.5,   99.5,  100.0,  0.70, NULL, '미정', FALSE, '%'),
  -- 코팅 · IPQC
  ('PROCESS', '코팅',     'INSP_ITEM', 'IT-CTH',   26.0,   22.0,   24.0,  0.70, NULL, '미정', FALSE, 'um'),
  ('PROCESS', '코팅',     'INSP_ITEM', 'IT-SPD',   13.0,    9.0,   11.0,  0.70, NULL, '미정', FALSE, 'm/min'),
  -- 적층·경화 · FQC
  ('PROCESS', '적층경화', 'INSP_ITEM', 'IT-THK',  205.0,  195.0,  200.0,  0.70, NULL, '미정', FALSE, 'um'),
  ('PROCESS', '적층경화', 'INSP_ITEM', 'IT-GLS',   92.0,   84.0,   88.0,  0.70, NULL, '미정', FALSE, 'GU'),
  ('PROCESS', '적층경화', 'INSP_ITEM', 'IT-COL',    1.00,   0.0,    0.30, 0.70, NULL, '미정', FALSE, 'dE'),
  ('PROCESS', '적층경화', 'INSP_ITEM', 'IT-ADH',   12.0,    6.0,    9.0,  0.70, NULL, '미정', TRUE, 'N/25mm'),
  -- 출하 · OQC
  ('PROCESS', '출하',     'INSP_ITEM', 'IT-THK',  205.0,  195.0,  200.0,  0.70, NULL, '미정', FALSE, 'um'),
  ('PROCESS', '출하',     'INSP_ITEM', 'IT-GLS',   92.0,   84.0,   88.0,  0.70, NULL, '미정', FALSE, 'GU'),
  ('PROCESS', '출하',     'INSP_ITEM', 'IT-DIM', 1010.0,  990.0, 1000.0,  0.70, NULL, '미정', FALSE, 'mm'),
  ('PROCESS', '출하',     'INSP_ITEM', 'IT-VFM',  NULL,   NULL,   NULL,   0.70, NULL, '미정', FALSE, NULL);
