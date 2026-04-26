// CloudFront Function — media auth (viewer-request)
// Lightweight auth check for /media/* paths.
//
// Validates: st-auth cookie present + valid JWT format (3 base64 parts).
// Security relies on: Secure + SameSite=Lax cookie (prevents CSRF),
// same-origin policy (prevents JS access from other domains),
// and the opaque UUID namespace in the S3 path (prevents guessing).
//
// Full JWT validation (signature, expiry, issuer) happens at the app layer.

function handler(event) {
  var request = event.request;
  var uri = request.uri;

  if (!uri.startsWith('/media/')) {
    return request;
  }

  var cookies = request.cookies || {};
  var authCookie = cookies['st-auth'];

  // Must have auth cookie
  if (!authCookie || !authCookie.value) {
    return {
      statusCode: 403,
      statusDescription: 'Forbidden',
      body: { encoding: 'text', data: 'Authentication required' }
    };
  }

  // Must be valid JWT format (header.payload.signature)
  var token = authCookie.value;
  if (token.length < 100 || token.split('.').length !== 3) {
    return {
      statusCode: 403,
      statusDescription: 'Forbidden',
      body: { encoding: 'text', data: 'Invalid token' }
    };
  }

  // Auth OK — pass through to S3 origin
  return request;
}
