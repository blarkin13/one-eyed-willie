/* Use real transparent title artwork when available, never a guessed font. */
(function () {
  const LOCAL_LOGO = /^\/api\/artwork\/[0-9a-f]{64}$/;
  function set(heading, title, url) {
    if (!heading) return;
    const text = String(title || 'Untitled');
    const request = {};
    heading._mediaLogoRequest = request;
    heading.classList.remove('has-title-logo');
    heading.textContent = text;
    if (typeof url !== 'string' || !LOCAL_LOGO.test(url)) return;
    const logo = new Image();
    logo.alt = ''; // An accessible, visually hidden text title remains in the h1/h3.
    logo.className = 'media-title-logo';
    logo.decoding = 'async';
    logo.onload = () => {
      if (heading._mediaLogoRequest !== request || !logo.naturalWidth) return;
      const label = document.createElement('span');
      label.className = 'media-title-accessible';
      label.textContent = text;
      heading.replaceChildren(label, logo);
      heading.classList.add('has-title-logo');
    };
    // Leave the original text heading unchanged on error.
    logo.src = url;
  }
  window.YarMediaTitleLogo = { set };
})();
