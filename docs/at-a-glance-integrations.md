# At a Glance – optional Yarr Media integrations

**Clock**, **Weather**, and **News** are independent first-party integrations,
all **disabled by default**. Each has four saved switches: enable the integration,
display on Home, display when the player is paused, and display on Idle.
**Ambient Display** is a fourth integration with a separate master on/off
switch and inactivity timeout (1, 2, 5, or 10 minutes); it defaults on but
has no effect unless a widget is enabled for Idle. Turning Ambient Display
off does not affect Home or Pause. The existing *Show in Integrations*
preference hides a tile without disabling its integration.

## Setup

1. Open **Settings → Integrations** on the Yarr Media server.
2. Expand Clock, Weather or News and enable it. Choose Home, Paused player
   and/or Idle screen independently.
3. Ambient Display: optionally disable the screensaver or choose its timeout.
4. Clock: select 12h/24h and device-local or a named time zone.
5. Weather: provide a five-digit **United States ZIP code**.
6. News: choose **NPR News** or **BBC News**.
7. You can also switch each integration on/off immediately on the
   **Integrations** hub without changing its placement preferences.

The Home screen shows a compact strip only for enabled Home widgets.
The browser and native Android TV players display pause widgets only
while the video is paused. The idle display appears after the configured inactivity timeout
(default: 120 seconds), can be dismissed with a key or pointer, and does not appear
while a video is playing, a dialog is open or a text field is being edited.
The TV native player reads settings on opening a video; reopen it for changes.

## Data providers and boundaries

- **Clock:** device clock, no Internet request. A selected IANA time zone
  adjusts display only.
- **Weather:** a US ZIP is resolved through `api.zippopotam.us` and the
  forecast is obtained from the [National Weather Service](https://www.weather.gov/documentation/services-web-api).
  The widget explicitly says *forecast*; it is not a weather-station
  real-time observation or a WeatherBug service. The ZIP and the resulting
  coordinates are sent to those services for the query. Weather results
  are cached server-side for approximately 15 minutes.
- **News:** headline titles and links from the selected publisher RSS feed,
  with publisher attribution. News is cached approximately five minutes.
  No article body, video, or images are republished. Check the
  publisher's distribution terms before a commercial public release.

The server contacts only fixed approved HTTPS provider hosts; no arbitrary
user-supplied URL may be fetched. If a provider is unavailable, the widget
shows an error instead of blocking the player. No integration uploads
media, scripts, personal watch history, or playback metadata.

This initial version does not include WeatherBug-branded forecasts,
weather radar, severe-weather alerts, location detection or multiple
custom RSS sources. Those can be planned separately after provider
licensing and user experience are confirmed.
