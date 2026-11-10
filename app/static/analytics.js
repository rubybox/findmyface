'use strict';
// Measurement ID is optional server configuration, never a credential.
fetch('/api/config').then(response => response.json()).then(config => {
  const id = config.analytics_measurement_id;
  if (!/^G-[A-Z0-9]+$/.test(id || '')) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function(){window.dataLayer.push(arguments);};
  window.gtag('js', new Date());
  window.gtag('config', id);
  const script = document.createElement('script');
  script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
  document.head.append(script);
}).catch(() => {}); // Analytics failure must never block photo search.
