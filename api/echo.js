export default function handler(req, res) {
  const { method, url, query } = req;
  res.status(200).json({ ok: true, method, url, query });
}
