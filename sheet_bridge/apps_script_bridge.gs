/**
 * Google Sheets -> Agent API 브리지
 * 초보자용: 시트 메뉴 버튼으로만 실행
 */

const CONFIG = {
  SHEET_NAME: 'products',
  AGENT_BASE_URL: 'https://YOUR-AGENT-URL', // 예: https://my-agent.onrender.com
  TIMEOUT_MS: 60000,
  AUTO_PUBLISH: true,
};

const COL = {
  source_url: 1,
  source_site: 2,
  title: 3,
  source_price_jpy: 4,
  target_price_krw: 5,
  estimated_margin_rate: 6,
  policy_risk: 7,
  approval_status: 8,
  publish_status: 9,
  market_product_id: 10,
  publish_message: 11,
  representative_image_url: 12,
  notes: 13,
  last_run_at: 14,
  image_urls: 15,
  source_description: 16,
  key_features: 17,
  specs_json: 18,
  llm_summary_ko: 19,
  llm_selling_points_ko: 20,
  llm_detail_outline_ko: 21,
  raw_text_snippet: 22,
  llm_product_judgement_ko: 23,
  llm_detail_sections_ko: 24,
};

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Agent 자동화')
    .addItem('선택 행 실행', 'runSelectedRows')
    .addItem('전체 행 실행', 'runAllRows')
    .addItem('헤더 만들기', 'ensureHeaders')
    .addToUi();
}

function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(CONFIG.SHEET_NAME);
  return sheet;
}

function ensureHeaders() {
  const sheet = getSheet_();
  const headers = Object.keys(COL);
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
}

function runSelectedRows() {
  const sheet = getSheet_();
  const range = sheet.getActiveRange();
  if (!range) return;
  const start = range.getRow();
  const num = range.getNumRows();
  processRows_(sheet, start, num);
}

function runAllRows() {
  const sheet = getSheet_();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  processRows_(sheet, 2, lastRow - 1);
}

function processRows_(sheet, startRow, numRows) {
  if (startRow < 2) startRow = 2;
  if (numRows <= 0) return;

  const values = sheet.getRange(startRow, 1, numRows, COL.llm_detail_sections_ko).getValues();
  const urls = [];
  const map = [];

  for (let i = 0; i < values.length; i++) {
    const url = String(values[i][COL.source_url - 1] || '').trim();
    if (!url) continue;
    urls.push(url);
    map.push(i);
  }
  if (urls.length === 0) return;

  const res = callAgentBatch_(urls);
  const now = new Date();

  for (let i = 0; i < res.length; i++) {
    const rowIndex = map[i];
    const out = res[i];

    values[rowIndex][COL.source_site - 1] = safe_(out, 'extraction.source_site');
    values[rowIndex][COL.title - 1] = safe_(out, 'extraction.title');
    values[rowIndex][COL.source_price_jpy - 1] = safe_(out, 'extraction.source_price_jpy');
    values[rowIndex][COL.target_price_krw - 1] = safe_(out, 'pricing.target_price_krw');
    values[rowIndex][COL.estimated_margin_rate - 1] = safe_(out, 'pricing.estimated_margin_rate');
    values[rowIndex][COL.policy_risk - 1] = safe_(out, 'policy.risk');
    values[rowIndex][COL.approval_status - 1] = safe_(out, 'approval_status');
    values[rowIndex][COL.publish_status - 1] = safe_(out, 'publish_status');
    values[rowIndex][COL.market_product_id - 1] = safe_(out, 'publish_result.market_product_id');
    values[rowIndex][COL.publish_message - 1] = safe_(out, 'publish_result.message');
    values[rowIndex][COL.representative_image_url - 1] = safe_(out, 'extraction.representative_image_url');
    values[rowIndex][COL.image_urls - 1] = stringifyList_(safe_(out, 'extraction.image_urls'));
    values[rowIndex][COL.source_description - 1] = safe_(out, 'extraction.source_description');
    values[rowIndex][COL.key_features - 1] = stringifyList_(safe_(out, 'extraction.key_features'));
    values[rowIndex][COL.specs_json - 1] = stringifyJson_(safe_(out, 'extraction.specs'));
    values[rowIndex][COL.llm_summary_ko - 1] = safe_(out, 'extraction.llm_summary_ko');
    values[rowIndex][COL.llm_selling_points_ko - 1] = stringifyList_(safe_(out, 'extraction.llm_selling_points_ko'));
    values[rowIndex][COL.llm_detail_outline_ko - 1] = stringifyList_(safe_(out, 'extraction.llm_detail_outline_ko'));
    values[rowIndex][COL.raw_text_snippet - 1] = safe_(out, 'extraction.raw_text_snippet');
    values[rowIndex][COL.llm_product_judgement_ko - 1] = safe_(out, 'extraction.llm_product_judgement_ko');
    values[rowIndex][COL.llm_detail_sections_ko - 1] = stringifyList_(safe_(out, 'extraction.llm_detail_sections_ko'));

    const notes = safe_(out, 'notes');
    values[rowIndex][COL.notes - 1] = Array.isArray(notes) ? notes.join(' | ') : '';
    values[rowIndex][COL.last_run_at - 1] = now;
  }

  sheet.getRange(startRow, 1, numRows, COL.llm_detail_sections_ko).setValues(values);
}

function callAgentBatch_(sourceUrls) {
  const url = CONFIG.AGENT_BASE_URL.replace(/\/$/, '') + '/run-link-batch';
  const payload = {
    source_urls: sourceUrls,
    auto_publish: CONFIG.AUTO_PUBLISH,
  };

  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify(payload),
  });

  const code = response.getResponseCode();
  const text = response.getContentText() || '';
  if (code >= 400) {
    throw new Error('Agent API 오류: ' + code + ' ' + text.slice(0, 500));
  }

  const json = JSON.parse(text);
  return json.results || [];
}

function safe_(obj, path) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length; i++) {
    if (cur == null) return '';
    cur = cur[parts[i]];
  }
  return cur == null ? '' : cur;
}

function stringifyList_(v) {
  if (!Array.isArray(v)) return '';
  return v.join(' | ');
}

function stringifyJson_(v) {
  if (!v || typeof v !== 'object') return '';
  try {
    return JSON.stringify(v);
  } catch (e) {
    return '';
  }
}
