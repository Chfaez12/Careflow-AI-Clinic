const API = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export async function request(path, { method = 'GET', body, headers = {}, ...options } = {}) {
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const response = await fetch(`${API}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...headers },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  return data;
}

export async function downloadFile(path, fallbackName) {
  const response = await fetch(`${API}${path}`, { credentials: 'include' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || data.message || `Download failed (${response.status})`);
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
