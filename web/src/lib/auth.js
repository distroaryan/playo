const API_BASE_URL = 'http://localhost:8000/api';

/**
 * Sends the Google ID token to the backend for verification and authentication.
 * @param {string} token - The Google ID token.
 * @returns {Promise<Object>} The authentication response (JWTs, merchant_id, etc.)
 */
export async function googleLogin(token) {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/google`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ token }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to authenticate with Google');
    }

    const data = await response.json();
    
    // Store tokens in localStorage for future requests
    if (data.access) {
      localStorage.setItem('accessToken', data.access);
      localStorage.setItem('refreshToken', data.refresh);
      localStorage.setItem('merchantId', data.merchant_id);
    }
    
    return data;
  } catch (error) {
    console.error('Google login error:', error);
    throw error;
  }
}
