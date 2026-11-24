export async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const keys = error.records?.length ? `：${error.records.join('、')}` : '';
    throw new Error((error.message || `请求失败 · ${response.status}`) + keys);
  }
  return response.json();
}

export function element(tag, text, attrs = {}) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  return node;
}

export function pretty(value) {
  return value !== null && typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? '—');
}
