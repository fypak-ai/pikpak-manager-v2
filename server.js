const express = require('express');
const cors = require('cors');
const axios = require('axios');

const app = express();
app.use(cors());
app.use(express.json());

const PIKPAK_API = 'https://api-drive.mypikpak.com';
const PIKPAK_AUTH = 'https://user.mypikpak.com';

const sessions = new Map();

async function pikpakRequest(endpoint, token, method = 'GET', body = null) {
  const url = `${PIKPAK_API}${endpoint}`;
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
  const config = { method, url, headers };
  if (body) config.data = body;
  return (await axios(config)).data;
}

// LOGIN
app.post('/api/login', async (req, res) => {
  const { method, access_token, device_id } = req.body;
  
  if (method === 'token' || method === 'force_token') {
    if (!access_token) return res.status(400).json({ error: 'Token required' });
    if (device_id) sessions.set(device_id, { access_token, refresh_token: '' });
    res.json({ success: true, access_token, user_id: 'user' });
  }
  else if (method === 'password') {
    // ... código original para login senha
  }
});

app.post('/api/auto-login', (req, res) => {
  const { device_id } = req.body;
  const session = sessions.get(device_id);
  if (!session?.access_token) return res.status(401).json({ error: 'No session' });
  res.json({ access_token: session.access_token });
});

// FILES
app.get('/api/files', async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) return res.status(401).json({ error: 'No token' });
  try {
    const data = await pikpakRequest(
      `/drive/v1/files?parent_id=${encodeURIComponent(req.query.parent_id || '')}&page_size=200`,
      token
    );
    res.json(data);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// FILE LINK
app.get('/api/file-link', async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token || !req.query.file_id) return res.status(400).json({ error: 'Missing params' });
  try {
    const data = await pikpakRequest(`/drive/v1/files/${req.query.file_id}?fields=medias`, token);
    res.json(data);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// SHARE
app.post('/api/share', async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  const { url, passcode } = req.body;
  if (!token || !url) return res.status(400).json({ error: 'Missing params' });
  const shareId = url.match(/s\/([^\/]+)/)?.[1];
  if (!shareId) return res.status(400).json({ error: 'Invalid URL' });
  try {
    const data = await pikpakRequest(`/drive/v1/shares/${shareId}`, token, 'POST', { passcode });
    res.json({ share_id: data.share_id, share_token: data.share_token, files: data.files || [] });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// DROPBOX
const { Dropbox } = require('dropbox');
app.post('/api/dropbox-test', async (req, res) => {
  const { Dropbox } = require('dropbox');
  const dbx = new Dropbox({ accessToken: req.body.token });
  const account = await dbx.usersGetCurrentAccount();
  res.json({ name: account.result.name.display_name });
});
app.post('/api/dropbox-send', async (req, res) => {
  const { token, folder, url, name } = req.body;
  const dbx = new Dropbox({ accessToken: token });
  const file = await axios.get(url, { responseType: 'arraybuffer' });
  await dbx.filesUpload({ path: `${folder}/${name}`, contents: file.data });
  res.json({ success: true });
});

app.use(express.static('public'));
app.listen(3000, () => console.log('Running on 3000'));
