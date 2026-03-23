const express = require('express');
const cors = require('cors');
const axios = require('axios');

const app = express();
app.use(cors());
app.use(express.json());

const PIKPAK_API = 'https://api-drive.mypikpak.com';
const PIKPAK_AUTH = 'https://user.mypikpak.com';

// In-memory storage for tokens (in production, use a database)
const sessions = new Map();

// Helper to make PikPak API requests
async function pikpakRequest(endpoint, token, method = 'GET', body = null) {
  const url = `${PIKPAK_API}${endpoint}`;
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
  
  const config = { method, url, headers };
  if (body) config.data = body;
  
  const response = await axios(config);
  return response.data;
}

// ==================== LOGIN ====================

// Login with access token
app.post('/api/login', async (req, res) => {
  const { method, access_token, device_id } = req.body;
  
  if (method === 'token' || method === 'force_token') {
    if (!access_token) {
      return res.status(400).json({ error: 'Access token required' });
    }
    
    try {
      // Validate token by getting user info
      const userInfo = await pikpakRequest('/drive/v1/about', access_token);
      
      // Store session
      if (device_id) {
        sessions.set(device_id, { access_token, refresh_token: '' });
      }
      
      res.json({ 
        success: true, 
        access_token,
        user_id: userInfo?.user_id || 'unknown'
      });
    } catch (error) {
      res.status(401).json({ 
        error: error.response?.data?.error_description || 'Invalid token' 
      });
    }
  }
  
  // Login with password
  else if (method === 'password') {
    const { username, password, captcha_token } = req.body;
    
    try {
      const authData = {
        client_id: 'pikpak',
        client_secret: 'Y3z6GEkwTxY',
        grant_type: 'password',
        username,
        password,
        device_id: device_id || 'web'
      };
      
      if (captcha_token) {
        authData.captcha_token = captcha_token;
      }
      
      const response = await axios.post(`${PIKPAK_AUTH}/v1/auth/token`, authData, {
        headers: { 'Content-Type': 'application/json' }
      });
      
      const { access_token, refresh_token } = response.data;
      
      if (device_id) {
        sessions.set(device_id, { access_token, refresh_token });
      }
      
      res.json({ success: true, access_token });
    } catch (error) {
      const errorData = error.response?.data;
      
      // Check if captcha or OTP is required
      if (errorData?.captcha_required) {
        return res.json({
          captcha_required: true,
          captcha_token: errorData.captcha_token,
          captcha_url: errorData.captcha_url
        });
      }
      
      if (errorData?.otp_required) {
        return res.json({
          otp_required: true,
          verification_id: errorData.verification_id,
          message: errorData.message,
          captcha_token: errorData.captcha_token
        });
      }
      
      res.status(401).json({ 
        error: errorData?.error_description || 'Login failed' 
      });
    }
  }
  
  // Login with OTP
  else if (method === 'otp') {
    const { username, password, code, verification_id, captcha_token } = req.body;
    
    try {
      const authData = {
        client_id: 'pikpak',
        client_secret: 'Y3z6GEkwTxY',
        grant_type: 'password',
        username,
        password,
        verification_id,
        code,
        device_id: device_id || 'web'
      };
      
      if (captcha_token) {
        authData.captcha_token = captcha_token;
      }
      
      const response = await axios.post(`${PIKPAK_AUTH}/v1/auth/token`, authData);
      const { access_token, refresh_token } = response.data;
      
      if (device_id) {
        sessions.set(device_id, { access_token, refresh_token });
      }
      
      res.json({ success: true, access_token });
    } catch (error) {
      res.status(401).json({ 
        error: error.response?.data?.error_description || 'Invalid code' 
      });
    }
  }
  
  else {
    res.status(400).json({ error: 'Invalid method' });
  }
});

// Auto-login with device_id
app.post('/api/auto-login', async (req, res) => {
  const { device_id } = req.body;
  
  const session = sessions.get(device_id);
  if (!session || !session.access_token) {
    return res.status(401).json({ error: 'No session found' });
  }
  
  try {
    // Validate token
    await pikpakRequest('/drive/v1/about', session.access_token);
    res.json({ access_token: session.access_token });
  } catch (error) {
    // Try refresh token
    if (session.refresh_token) {
      try {
        const response = await axios.post(`${PIKPAK_AUTH}/v1/auth/token`, {
          client_id: 'pikpak',
          client_secret: 'Y3z6GEkwTxY',
          grant_type: 'refresh_token',
          refresh_token: session.refresh_token
        });
        
        session.access_token = response.data.access_token;
        session.refresh_token = response.data.refresh_token;
        
        res.json({ access_token: session.access_token });
      } catch (refreshError) {
        sessions.delete(device_id);
        res.status(401).json({ error: 'Session expired' });
      }
    } else {
      res.status(401).json({ error: 'Session expired' });
    }
  }
});

// ==================== FILES ====================

app.get('/api/files', async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  const parent_id = req.query.parent_id || '';
  
  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }
  
  try {
    const data = await pikpakRequest(
      `/drive/v1/files?parent_id=${encodeURIComponent(parent_id)}&page_size=200`,
      token
    );
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.response?.data?.error_description || 'Failed to fetch files' });
  }
});

// ==================== FILE LINK ====================

app.get('/api/file-link', async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  const file_id = req.query.file_id;
  
  if (!token || !file_id) {
    return res.status(400).json({ error: 'Missing parameters' });
  }
  
  try {
    const data = await pikpakRequest(
      `/drive/v1/files/${file_id}?fields=medias`,
      token
    );
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.response?.data?.error_description || 'Failed to get link' });
  }
});

// ==================== SHARE ====================

app.post('/api/share', async (req, res) => {
  const token = req.headers.authorization?.replace('Bearer ', '');
  const { url, passcode } = req.body;
  
  if (!token || !url) {
    return res.status(400).json({ error: 'Missing parameters' });
  }
  
  try {
    // Extract share ID from URL
    const shareIdMatch = url.match(/s\/([^\/]+)/);
    if (!shareIdMatch) {
      return res.status(400).json({ error: 'Invalid share URL' });
    }
    
    const shareId = shareIdMatch[1];
    
    // Get share info
    const shareInfo = await pikpakRequest(
      `/drive/v1/shares/${shareId}`,
      token,
      'POST',
      { passcode }
    );
    
    res.json({
      share_id: shareInfo.share_id,
      share_token: shareInfo.share_token,
      files: shareInfo.files || []
    });
  } catch (error) {
    res.status(500).json({ error: error.response?.data?.error_description || 'Failed to extract share' });
  }
});

// ==================== DROPBOX ====================

const { Dropbox } = require('dropbox');

app.post('/api/dropbox-test', async (req, res) => {
  const { token } = req.body;
  
  if (!token) {
    return res.status(400).json({ error: 'Token required' });
  }
  
  try {
    const dbx = new Dropbox({ accessToken: token });
    const account = await dbx.usersGetCurrentAccount();
    res.json({ name: account.result.name.display_name });
  } catch (error) {
    res.status(401).json({ error: 'Invalid Dropbox token' });
  }
});

app.post('/api/dropbox-send', async (req, res) => {
  const { token, folder, url, name } = req.body;
  
  if (!token || !url) {
    return res.status(400).json({ error: 'Missing parameters' });
  }
  
  try {
    const dbx = new Dropbox({ accessToken: token });
    
    // Download file from URL
    const response = await axios.get(url, { responseType: 'arraybuffer' });
    const fileBuffer = Buffer.from(response.data);
    
    // Upload to Dropbox
    const path = `${folder}/${name}`;
    await dbx.filesUpload({ path, contents: fileBuffer });
    
    res.json({ success: true, path });
  } catch (error) {
    res.status(500).json({ error: error.message || 'Failed to upload to Dropbox' });
  }
});

// ==================== STATIC FILES ====================

app.use(express.static('public'));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`PikPak Manager v2 running on port ${PORT}`);
});
