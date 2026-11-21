// yarr.media/how2s: setup guides. Rendered by worker.js inside the shared
// site header and footer (siteChrome). Content blocks:
//   'text'            paragraph; supports `code`, **bold** and [label](url)
//   {code:'...'}      command / file block
//   {steps:[...]}     numbered list     {list:[...]}  bulleted list
//   {note:'...'}      highlighted tip

const RIGHTS_NOTE = {note:'Only download media you have the rights to. Yarr Media plays files from your own folders and does not supply movies, shows or music.'};
const COMPOSE = (name, port) => `sudo mkdir -p /opt/${name} && cd /opt/${name}
sudo tee compose.yaml > /dev/null <<'EOF'
services:
  ${name}:
    image: lscr.io/linuxserver/${name}:latest
    container_name: ${name}
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Chicago
    volumes:
      - ./config:/config
      - /srv/data:/data
    ports:
      - ${port}:${port}
    restart: unless-stopped
EOF
sudo docker compose up -d`;
const IDS_NOTE = 'Change `PUID`/`PGID` to your own numbers (run `id`; usually 1000) and `TZ` to your time zone (run `timedatectl show -p Timezone --value`). The `/srv/data:/data` line gives the app the same folders as the other apps, so finished downloads are moved into your library instantly instead of copied.';
const UPDATE = name => ['Updating', ['The image is updated by pulling the new version and recreating the container. Your settings in `/opt/'+name+'/config` are kept.', {code:'cd /opt/'+name+' && sudo docker compose pull && sudo docker compose up -d'}]];
const BEFORE_APPS = ['Before you start', [{list:[
 'A server with Docker: [Set up a Debian or Ubuntu server](/how2s/linux-server) and [Install Docker](/how2s/docker). The Yarr Media installer already installs Docker.',
 'The `/srv/data` folders from the server guide (`/srv/data/media/…` for your library and `/srv/data/usenet/…` for downloads).',
 'The server\'s address on your network, for example `192.168.1.50` (run `hostname -I` on the server). Replace `SERVER-IP` below with it.']}]];

function arrGuide({slug, name, port, folder, category, adds, extra}) {
 return {slug, group:'apps', title:'Set up '+name, minutes:15,
  summary:name+' '+({sonarr:'watches for new episodes of your TV shows',radarr:'manages your movie collection',lidarr:'manages your music by artist and album'})[slug]+', sends downloads to SABnzbd and files the results into your library.',
  sections:[BEFORE_APPS,
  ['1. Start '+name, [{code:COMPOSE(slug, port)}, IDS_NOTE]],
  ['2. Open '+name+' and protect it', [
   'Open `http://SERVER-IP:'+port+'` in a browser. The first time, '+name+' asks you to choose how to sign in: pick **Forms (Login Page)**, set a username and password, and save. You can choose **Disabled for Local Addresses** if you only use it at home.']],
  ['3. Set the library folder', [{steps:[
   'Go to **Settings → Media Management**.',
   'Under **Root Folders**, choose **Add Root Folder** and select `'+folder+'`.',
   ...(extra||[]),
   'Choose **Save Changes**.']},
   name+' names and files everything the way Yarr Media expects (see [Organize your media folders](/how2s/media-folders)).']],
  ['4. Connect SABnzbd', [{steps:[
   'Go to **Settings → Download Clients** and choose **+**, then **SABnzbd**.',
   '**Host**: `SERVER-IP` (not `localhost`; each app runs in its own container). **Port**: `8080`.',
   '**API Key**: SABnzbd\'s API key (SABnzbd → Config → General → Security).',
   '**Category**: `'+category+'`.',
   'Choose **Test**, then **Save**.']},
   'No SABnzbd yet? See [Set up SABnzbd](/how2s/sabnzbd).']],
  ['5. Add indexers', ['Indexers are how '+name+' searches. The easiest way to manage them is [Prowlarr](/how2s/prowlarr): add your indexers there once and it fills them in for '+name+' automatically.']],
  ['6. Connect '+name+' to Yarr Media', [{steps:[
   'In '+name+', go to **Settings → General** and copy the **API Key**.',
   'In Yarr Media, go to **Settings → Integrations → '+name+'**.',
   'Enter the address `http://SERVER-IP:'+port+'` and paste the API key, then choose **Connect '+name+'**.']},
   'Yarr Media can now use '+name+' for '+adds+' and send new titles to it. When a download finishes, '+name+' moves it into `'+folder+'` and it appears in your Yarr library at the next scan.']],
  UPDATE(slug), ['Good to know', [RIGHTS_NOTE]]]};
}

export const HOW2S = [
 {slug:'linux-server', group:'server', title:'Set up a Debian or Ubuntu server', minutes:45,
  summary:'Turn a spare PC or mini PC into a home server for Yarr Media, ready to reach from your other computers.',
  sections:[
  ['What you need', [{list:[
   'A 64-bit computer (Intel/AMD or ARM) with at least 4 GB of memory. A mini PC is ideal. Recent Intel processors help Yarr convert videos that a TV can\'t play directly.',
   'A drive for your media (internal or USB), and a wired network connection if possible.',
   'A USB stick of 4 GB or more for the installer. It will be erased.']}]],
  ['1. Download Linux', ['Either of these works well. Ubuntu\'s installer is a little friendlier; Debian is lighter.', {list:[
   '**Ubuntu Server 26.04 LTS**: [ubuntu.com/download/server](https://ubuntu.com/download/server)',
   '**Debian 13 "trixie"**: [debian.org/download](https://www.debian.org/download) (the small "netinst" image)']}]],
  ['2. Make a USB installer', ['Write the downloaded `.iso` file to the USB stick with [balenaEtcher](https://etcher.balena.io) (Windows, Mac, Linux) or [Rufus](https://rufus.ie) (Windows).']],
  ['3. Install', [
   'Plug the stick into the server and start it from USB (usually by pressing F12, F10, F11 or Esc while it starts). Then:', {list:[
   '**Ubuntu Server**: follow the prompts, use the entire system disk, and tick **Install OpenSSH server**. Skip the optional snaps.',
   '**Debian**: choose **Install**. Leave the root password empty (your own user then gets `sudo`). Use guided partitioning on the system disk. At **Software selection**, untick the desktop environments and tick **SSH server** and **standard system utilities**.']},
   {note:'Pick the system disk carefully when partitioning: the installer erases the disk you choose. If your media drive is already connected and full, unplug it during installation.'}]],
  ['4. Give it a fixed address and log in from your computer', [
   'Sign in on the server and find its address:', {code:'hostname -I'},
   'In your router\'s settings, reserve this address for the server (often called **DHCP reservation** or **static lease**) so it never changes. From now on you can work from your own computer (Terminal on Mac and Linux, Terminal or PowerShell on Windows):',
   {code:'ssh yourname@192.168.1.50'}]],
  ['5. Update and keep it updated', [
   {code:'sudo apt update && sudo apt full-upgrade -y\nsudo apt install -y unattended-upgrades\nsudo dpkg-reconfigure -plow unattended-upgrades'},
   'The last command turns on automatic security updates (answer **Yes**). Ubuntu has them on already.']],
  ['6. Add your media drive', [
   'List the drives and note your media drive\'s name (like `sdb1`), `UUID` and `FSTYPE`:', {code:'lsblk -f'},
   '**A new, empty drive** can be formatted for Linux. This erases it, so double-check the name:',
   {code:'sudo parted /dev/sdb --script mklabel gpt mkpart media ext4 0% 100%\nsudo mkfs.ext4 -L media /dev/sdb1'},
   'Mount it at `/srv/data` every time the server starts (run `lsblk -f` again to get the new UUID). Use `ext4` for a Linux drive, or `ntfs3` with `,uid=1000,gid=1000` added after `nofail` for a drive formatted on Windows:',
   {code:'sudo mkdir -p /srv/data\necho "UUID=PASTE-UUID-HERE /srv/data ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab\nsudo systemctl daemon-reload && sudo mount -a\ndf -h /srv/data'}]],
  ['7. Create the folders', [
   'These are the folders every guide on this site uses. The `usenet` folders are only needed if you use [SABnzbd](/how2s/sabnzbd).',
   {code:'sudo mkdir -p /srv/data/media/{movies,tv,music} /srv/data/usenet/{incomplete,complete}\nsudo chown -R $USER:$USER /srv/data'},
   'Already have media? Move it into `movies`, `tv` and `music` (see [Organize your media folders](/how2s/media-folders)).']],
  ['Next', ['[Install Yarr Media](/how2s/yarr-media). It installs Docker for you.']]]},

 {slug:'docker', group:'server', title:'Install Docker', minutes:10,
  summary:'Docker runs Yarr Media and the optional apps in tidy, self-contained containers. Install it yourself, or let the Yarr Media installer do it.',
  sections:[
  ['Do you need this guide?', ['The [Yarr Media installer](/how2s/yarr-media) installs Docker automatically if it is missing. Use this guide if you want Docker in place first, for example to run the download apps before Yarr Media.']],
  ['1. Add Docker\'s package repository', ['These commands follow Docker\'s official instructions and work on both Debian and Ubuntu:',
   {code:`sudo apt update && sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
. /etc/os-release
sudo curl -fsSL https://download.docker.com/linux/$ID/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/$ID
Suites: \${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update`}]],
  ['2. Install Docker and Compose', [{code:'sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin'}]],
  ['3. Check it works', [{code:'sudo docker run --rm hello-world\ndocker compose version'}, 'You should see "Hello from Docker!" and a Compose version number.']],
  ['Optional: use Docker without sudo', [{code:'sudo usermod -aG docker $USER'}, 'Log out and back in for it to take effect.',
   {note:'Members of the docker group effectively have full control of the server. Only add accounts you trust.'}]],
  ['Everyday commands', [{list:[
   '`sudo docker ps`: what is running',
   '`sudo docker logs -f sonarr`: follow an app\'s log (Ctrl+C to stop)',
   '`sudo docker compose up -d`: start the app in the current folder',
   '`sudo docker compose pull && sudo docker compose up -d`: update it',
   '`sudo docker compose down`: stop and remove it (its settings folder is kept)']}]],
  ['More', ['Docker\'s own guides: [Debian](https://docs.docker.com/engine/install/debian/), [Ubuntu](https://docs.docker.com/engine/install/ubuntu/).']]]},

 {slug:'yarr-media', group:'yarr', title:'Install Yarr Media', minutes:10,
  summary:'Install the Yarr Media server with one command, add your libraries and start watching in any browser at home.',
  sections:[
  ['Before you start', [{list:[
   'A 64-bit Linux computer: see [Set up a Debian or Ubuntu server](/how2s/linux-server).',
   'A folder with your media, for example `/srv/data/media` with `movies`, `tv` and `music` inside.']}]],
  ['1. Run the installer', [{code:'curl -fsSL https://yarr.media/install.sh | sudo bash'},
   'It installs Docker if needed, asks which folder holds your media (enter `/srv/data/media`), and starts Yarr Media. It also sets up the secure front door used by [remote access](/how2s/remote-access) and turns on nightly updates.',
   'Prefer apt? See [Install with apt](/apt).']],
  ['2. Open Yarr Media', ['On any computer or phone on your home network, open:', {code:'http://SERVER-IP:8787'}, 'Replace `SERVER-IP` with the address the installer printed at the end.']],
  ['3. Add your libraries', [{steps:[
   'Go to **Settings → Libraries** and choose **+ Add library**.',
   'Give it a name, choose the **Library type** (Movies, TV Shows or Music) and pick its folder. Your media folder appears as `/media`, so movies are in `/media/movies`.',
   'Save. Yarr Media scans the folder and fetches posters, descriptions and cast.',
   'Repeat for TV shows and music.']},
   'Yarr Media only reads your media folder. It never changes, moves or deletes your files.']],
  ['4. Optional extras', [{list:[
   '**Better artwork**: Settings → Metadata. TV details work out of the box; adding a TMDB token adds more artwork and summaries.',
   '**Subtitles**: [Add subtitles with OpenSubtitles](/how2s/opensubtitles).',
   '**On your TV**: [Install the Google TV app](/how2s/google-tv).',
   '**Away from home**: [Watch away from home (Pro)](/how2s/remote-access).']}]],
  ['Updates, settings and uninstalling', [{list:[
   'Updates install automatically each night. To update now: `sudo yarr-media-update`.',
   'To change the media folder or other settings, run the installer again. Your library and watch history are kept.',
   'Installer options: `YARR_MEDIA_DIR=/path`, `YARR_PORT=8787`, `YARR_NO_REMOTE=1` (home network only), for example `curl -fsSL https://yarr.media/install.sh | sudo YARR_NO_REMOTE=1 bash`.',
   'View the log: `sudo docker logs -f yarr-media`.',
   'Uninstall: `sudo yarr-media-uninstall` removes everything Yarr Media added (containers, images, update timer, the router forward, `/opt/yarr-media` and `/var/lib/yarr-media`). Add `--keep-data` to keep your library database. Your media folders are never changed: Yarr Media only reads them.']}]]]},

 {slug:'media-folders', group:'yarr', title:'Organize your media folders', minutes:5,
  summary:'Name folders and files so Yarr Media matches every movie, episode and album correctly.',
  sections:[
  ['The layout', ['Keep one top folder per kind of media:', {code:'/srv/data/media/\n├── movies/\n├── tv/\n└── music/'}]],
  ['Movies', ['One folder per movie, with the year:', {code:'movies/Blade Runner (1982)/Blade Runner (1982).mkv\nmovies/Arrival (2016)/Arrival (2016).mp4'}]],
  ['TV shows', ['A folder per show, a folder per season, and the season and episode number in every file name:', {code:'tv/The Expanse (2015)/Season 01/The Expanse (2015) - S01E01 - Dulcinea.mkv\ntv/The Expanse (2015)/Season 01/The Expanse (2015) - S01E02 - The Big Empty.mkv'}, 'Use `Season 00` for specials.']],
  ['Music', [{code:'music/Daft Punk/Discovery (2001)/01 - One More Time.flac'}, 'Yarr Media also reads the tags inside your music files.']],
  ['Subtitles', ['Put subtitle files (`.srt`, `.vtt`, `.ass`, `.ssa`) next to the video with the same name, plus the language:', {code:'Arrival (2016).mkv\nArrival (2016).en.srt\nArrival (2016).es.srt'}]],
  ['Tips', [{list:[
   'Adding the year avoids mix-ups between remakes and shows with the same name.',
   '[Sonarr](/how2s/sonarr), [Radarr](/how2s/radarr) and [Lidarr](/how2s/lidarr) name files this way automatically.',
   'After renaming lots of files, start a scan from **Settings → Libraries**.']}]]]},

 {slug:'google-tv', group:'yarr', title:'Install the Google TV app', minutes:10,
  summary:'Put Yarr Media on a Google TV or Android TV with the Downloader app, and connect it to your server.',
  sections:[
  ['1. Install Downloader', ['On the TV, open the Play Store and install **Downloader** by AFTVnews.']],
  ['2. Allow Downloader to install apps', ['Open **Settings → Apps → Security & restrictions → Unknown sources** and turn on **Downloader**. The menu names vary a little between TV models; if you don\'t see it, Downloader will ask the first time it installs something.']],
  ['3. Download Yarr Media', [{steps:[
   'Open Downloader and enter `yarr.media/tv`.',
   'Choose **Go**. The app downloads.',
   'Choose **Install**, then **Open**.']}]],
  ['4. Connect to your server', ['The app looks for your Yarr Media server on your home network. If it doesn\'t find it, open **Server settings**, enter `http://SERVER-IP:8787` and choose **Connect**.']],
  ['5. Optional: sign in to your Yarr account', [{steps:[
   'Open **Server settings → Yarr account**. The TV shows a short code.',
   'On your phone or computer, go to [yarr.media/activate](/activate), sign in and enter the code.']},
   'You can sign the TV out at any time from **My Account**.']],
  ['Updating', ['Repeat step 3. The new version installs over the old one and keeps your settings.']]]},

 {slug:'remote-access', group:'yarr', title:'Watch away from home (Pro)', minutes:15,
  summary:'Reach your own library from anywhere at app.yarr.media, streaming straight from your server.',
  sections:[
  ['How it works', ['[app.yarr.media](https://app.yarr.media) signs you in and then connects your browser directly to your own server over HTTPS. Your movies and shows stream from your server to your device; they are never uploaded to or relayed through Yarr Media. Every remote request carries a short-lived signed pass that your server checks itself.']],
  ['Before you start', [{list:[
   'Yarr Media Pro on your account.',
   'Your server installed with the [Yarr Media installer](/how2s/yarr-media) (it includes the secure front door).',
   'Access to your router\'s settings.']}]],
  ['1. Connect your server to your account', [{steps:[
   'In Yarr Media, go to **Settings → General → Connect to Yarr**. It shows a pairing code.',
   'Go to [My Account](/account), sign in and enter the code.']}]],
  ['2. Open port 443', [
   'Your router needs to pass secure web traffic to the server. The installer tries to do this automatically (UPnP). If that didn\'t work, add a port-forwarding rule in your router:', {list:[
   '**Protocol**: TCP. **External port**: 443. **Internal address**: `SERVER-IP`. **Internal port**: 443.']},
   {note:'Only forward port 443. Don\'t forward 8787: that port is for your home network.'}]],
  ['3. Check it', ['On [My Account](/account), choose **Check remote access**. When it reports that your server is reachable, open [app.yarr.media](https://app.yarr.media) on your phone or laptop away from home.']],
  ['If the check fails', [{list:[
   '**Your internet provider may share one public address among many customers** (called CGNAT). If your router\'s internet (WAN) address starts with `100.64` to `100.127`, or doesn\'t match the address websites see, ask your provider for a public IP address.',
   '**Something else uses port 443** on your router or server. Only one device can receive it.',
   '**The server is off or asleep.** Remote access needs it running.',
   'Your home address changing is fine: the server reports its new address automatically.']}]]]},

 {slug:'barnacles', group:'yarr', title:'Share with friends (Barnacles)', minutes:5,
  summary:'Let family and friends watch the libraries you choose, on their own TV, phone or browser, under your Pro.',
  sections:[
  ['How it works', ['A barnacle is someone you share your server with. They need only a free Yarr Media account, no media and no Pro of their own. They watch the libraries you pick, with their own Continue Watching and watched marks, and can\'t change anything on your server. Video streams straight from your server to them.']],
  ['Before you start', [{list:[
   'Yarr Media Pro on your account, and [remote access](/how2s/remote-access) working.',
   'Your server updated to the latest Yarr Media (it then lists its libraries on My Account).']}]],
  ['1. Invite them', [{steps:[
   'Go to [My Account](/account) and find **Barnacles**.',
   'Enter the email of their Google account and tick the libraries they can see.',
   'Choose **Invite barnacle**.']}]],
  ['2. They accept', [{steps:[
   'They sign in at [yarr.media](/account) with that Google account.',
   'Under **Shared with you**, they choose **Accept**.']}]],
  ['3. They watch', [{list:[
   '**Google TV or Android phone**: install the app ([TV](/how2s/google-tv), or yarr.media/android on a phone) and sign in with **Yarr account**. If they also have their own server, **Choose server** switches between them.',
   '**Browser**: **Open in your browser** under Shared with you, or [app.yarr.media](https://app.yarr.media).']}]],
  ['Changing or ending access', ['On My Account, **Change libraries** or **Remove** next to each barnacle. Changes reach devices that are already watching within the hour. Barnacles can leave at any time from Shared with you.',
   {note:'Only share media you have the rights to share.'}]]]},

 {slug:'opensubtitles', group:'yarr', title:'Add subtitles with OpenSubtitles', minutes:5,
  summary:'Search for and download subtitles from inside the Yarr Media player.',
  sections:[
  ['1. Get an API key', [{steps:[
   'Create a free account at [opensubtitles.com](https://www.opensubtitles.com).',
   'Go to [API Consumers](https://www.opensubtitles.com/en/consumers) and create a new consumer.',
   'Copy its **API key**.']}]],
  ['2. Connect it to Yarr Media', [{steps:[
   'Go to **Settings → Integrations → OpenSubtitles**.',
   'Paste the API key. Leave **Account token** empty unless downloads ask for it.',
   'Choose **Connect OpenSubtitles**.']},
   'The key is saved on your server and is never shown again.']],
  ['3. Use it', ['While a video plays, open the subtitles menu and search. Downloaded subtitles are saved for next time. Free OpenSubtitles accounts have a daily download limit.']],
  ['Have your own subtitle files?', ['Put them next to the video instead: see [Organize your media folders](/how2s/media-folders#subtitles).']]]},

 {slug:'sabnzbd', group:'apps', title:'Set up SABnzbd', minutes:15,
  summary:'SABnzbd downloads from Usenet. Sonarr, Radarr and Lidarr hand it what to download, and Yarr Media shows its queue.',
  sections:[BEFORE_APPS,
  ['1. Start SABnzbd', [{code:COMPOSE('sabnzbd', 8080)}, IDS_NOTE]],
  ['2. Run the quick-start wizard', [
   'Open `http://SERVER-IP:8080`. The wizard asks for your language and the server details from your Usenet provider: host, port (usually 563 with **SSL** on), username, password and number of connections. Choose **Test Server**, then finish the wizard.']],
  ['3. Set the folders', [{steps:[
   'Go to **Config (gear icon) → Folders**.',
   '**Temporary Download Folder**: `/data/usenet/incomplete`.',
   '**Completed Download Folder**: `/data/usenet/complete`.',
   'Choose **Save Changes**.']}]],
  ['4. Add categories', ['Go to **Config → Categories** and add `tv`, `movies` and `music` (leave the folder empty; SABnzbd uses the category name). Sonarr, Radarr and Lidarr use these to tell their downloads apart.']],
  ['5. Copy the API key', ['Go to **Config → General → Security** and copy the **API Key**. You need it for Sonarr, Radarr, Lidarr and Yarr Media.']],
  ['6. Connect SABnzbd to Yarr Media', [{steps:[
   'In Yarr Media, go to **Settings → Integrations → SABnzbd**.',
   'Enter the address `http://SERVER-IP:8080` and paste the API key, then choose **Connect SABnzbd**.']},
   'The SABnzbd page in Yarr Media now shows the queue and history, with pause and resume.']],
  ['If you see "Access denied"', ['SABnzbd only accepts the names it knows. Using the IP address always works. To use a name like `http://myserver:8080`, add it under **Config → Special → host_whitelist**.']],
  UPDATE('sabnzbd'), ['Good to know', [RIGHTS_NOTE]]]},

 arrGuide({slug:'sonarr', name:'Sonarr', port:8989, folder:'/data/media/tv', category:'tv', adds:'TV show details',
  extra:['Turn on **Rename Episodes** so files get season and episode numbers.']}),
 arrGuide({slug:'radarr', name:'Radarr', port:7878, folder:'/data/media/movies', category:'movies', adds:'movie artwork and details',
  extra:['Turn on **Rename Movies** so each movie gets its own `Title (Year)` folder.']}),
 arrGuide({slug:'lidarr', name:'Lidarr', port:8686, folder:'/data/media/music', category:'music', adds:'your artists and albums',
  extra:['Choose a quality profile and metadata profile for the root folder when asked.']}),

 {slug:'prowlarr', group:'apps', title:'Set up Prowlarr', minutes:10,
  summary:'Prowlarr keeps your indexers in one place and shares them with Sonarr, Radarr and Lidarr.',
  sections:[BEFORE_APPS,
  ['1. Start Prowlarr', [{code:COMPOSE('prowlarr', 9696).replace('      - /srv/data:/data\n','')},
   'Change `PUID`, `PGID` and `TZ` as in the other guides. Prowlarr doesn\'t need your media folders.']],
  ['2. Open Prowlarr and protect it', ['Open `http://SERVER-IP:9696` and set up a login (**Forms (Login Page)**) when asked.']],
  ['3. Add your indexers', [{steps:[
   'Go to **Indexers → Add Indexer**.',
   'Search for the indexer you use and select it.',
   'Fill in its details (usually an API key from your account on the indexer\'s website).',
   'Choose **Test**, then **Save**.']}]],
  ['4. Connect your apps', [{steps:[
   'Go to **Settings → Apps** and choose **+**, then **Sonarr**.',
   '**Prowlarr Server**: `http://SERVER-IP:9696`. **Sonarr Server**: `http://SERVER-IP:8989`.',
   '**API Key**: Sonarr\'s API key (Sonarr → Settings → General).',
   'Choose **Test**, then **Save**.',
   'Repeat for Radarr (`http://SERVER-IP:7878`) and Lidarr (`http://SERVER-IP:8686`).']},
   'Prowlarr now adds your indexers to every app and keeps them in sync. Check Sonarr\'s **Settings → Indexers** to see them appear.']],
  UPDATE('prowlarr'), ['Good to know', [RIGHTS_NOTE]]]}
];

export const HOW2_GROUPS = [
 ['server','Get your server ready','A home server you can reach from your other devices.'],
 ['yarr','Yarr Media','Install, organize and watch, at home and away.'],
 ['apps','Optional apps','Popular companion apps that Yarr Media can connect to. They are separate projects, set up and managed on their own.']];

const esc = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function inline(text) {
 return esc(text)
  .replace(/`([^`]+)`/g, '<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  .replace(/\[([^\]]+)\]\(((?:https:\/\/|\/)[^)\s]*)\)/g, (_, label, href) => '<a href="'+href+'"'+(href.startsWith('https://')&&!href.startsWith('https://yarr.media')&&!href.startsWith('https://app.yarr.media')?' rel="noopener"':'')+'>'+label+'</a>');
}
const block = b => typeof b === 'string' ? '<p>'+inline(b)+'</p>'
 : b.code ? '<pre><code>'+esc(b.code)+'</code></pre>'
 : b.steps ? '<ol>'+b.steps.map(s=>'<li>'+inline(s)+'</li>').join('')+'</ol>'
 : b.list ? '<ul>'+b.list.map(s=>'<li>'+inline(s)+'</li>').join('')+'</ul>'
 : b.note ? '<p class="how2-note">'+inline(b.note)+'</p>' : '';
const anchor = h => h.toLowerCase().replace(/^\d+\.\s*/,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');

const HOW2_CSS = ':root{color-scheme:dark}*{box-sizing:border-box}html{scroll-behavior:smooth}body{background:radial-gradient(ellipse at 85% 5%,#3b111144,transparent 36%),#0a0a0a}'+
 'main{padding:64px 0 80px;max-width:880px}.eyebrow{color:#ea8787;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.17em}.eyebrow a{text-decoration:none}'+
 'h1{font-size:clamp(36px,5.5vw,58px);letter-spacing:-.045em;line-height:1.1;margin:16px 0 18px}h2{font-size:22px;margin:0 0 12px}p,li{color:#cdc7be;line-height:1.75;font-size:16px}.intro{font-size:19px;margin-bottom:10px}.meta{color:#a9a29a;font-size:14px;margin:0 0 30px}'+
 '.how2-section{padding:24px 0;border-top:1px solid #ffffff25;scroll-margin-top:20px}.how2-section p{margin:0 0 12px}.how2-section ol,.how2-section ul{margin:0 0 12px;padding-left:24px}li{margin:4px 0}'+
 'code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em;background:#ffffff14;border-radius:5px;padding:2px 6px;color:#f5f1e8;overflow-wrap:anywhere}'+
 'pre{background:#141414;border:1px solid #ffffff22;border-radius:10px;padding:16px 18px;overflow-x:auto;margin:0 0 14px}pre code{background:none;padding:0;font-size:14px;line-height:1.6;white-space:pre;overflow-wrap:normal}'+
 '.how2-note{border-left:3px solid #a61e1e;background:#a61e1e14;padding:12px 16px;border-radius:0 8px 8px 0}main a{color:#f0a3a3;text-decoration-color:#a61e1e}main a:hover{color:#fff}'+
 '.how2-group{margin:44px 0 0}.how2-group>p{margin:0 0 16px}.how2-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}'+
 '.how2-card{display:block;border:1px solid #ffffff26;border-radius:12px;padding:18px 18px 16px;text-decoration:none;color:#f5f1e8;background:#ffffff06;transition:background .2s,border-color .2s}.how2-card:hover{background:#ffffff10;border-color:#a61e1e}'+
 '.how2-card strong{display:block;font-size:17px;margin-bottom:6px}.how2-card span{display:block;color:#bdb6ad;font-size:14px;line-height:1.55}.how2-card small{display:block;color:#958e86;font-size:12px;margin-top:10px}main .how2-card{color:#f5f1e8}'+
 '.how2-pager{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:34px;padding-top:24px;border-top:1px solid #ffffff25}.how2-pager a{text-decoration:none}'+
 '@media(max-width:600px){main{padding:44px 0}p,li{font-size:15px}pre code{font-size:13px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.how2-card{transition:none}}';

function page(title, description, path, body) {
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+
  '<title>'+esc(title)+' | Yarr Media</title><meta name="description" content="'+esc(description)+'"><meta name="robots" content="index,follow"><link rel="canonical" href="https://yarr.media'+path+'">'+
  '<style>'+HOW2_CSS+'</style></head><body><div class="wrap"><header class="nav"></header><main>'+body+'</main><footer class="foot"></footer></div></body></html>';
}

export const HOW2_PATHS = ['/how2s', ...HOW2S.map(g => '/how2s/'+g.slug)];

export function how2Html(path) {
 const p = path.replace(/\/+$/,'') || '/';
 if (p === '/how2s') {
  const groups = HOW2_GROUPS.map(([id,name,blurb]) => '<section class="how2-group" aria-labelledby="g-'+id+'"><h2 id="g-'+id+'">'+esc(name)+'</h2><p>'+esc(blurb)+'</p><div class="how2-grid">'+
   HOW2S.filter(g=>g.group===id).map(g=>'<a class="how2-card" href="/how2s/'+g.slug+'"><strong>'+esc(g.title)+'</strong><span>'+esc(g.summary)+'</span><small>About '+g.minutes+' minutes</small></a>').join('')+'</div></section>').join('');
  return page('Setup guides','Step-by-step guides for setting up a Linux home server, Docker, Yarr Media and the apps it connects to.','/how2s',
   '<div class="eyebrow">Guides</div><h1>Set up Yarr Media, step by step.</h1><p class="intro">From a bare computer to watching your own library on every screen. Start at the top, or jump to what you need.</p>'+groups);
 }
 const m = /^\/how2s\/([a-z0-9-]+)$/.exec(p);
 const i = m ? HOW2S.findIndex(g => g.slug === m[1]) : -1;
 if (i < 0) return null;
 const g = HOW2S[i], prev = HOW2S[i-1], next = HOW2S[i+1];
 const sections = g.sections.map(([h, blocks]) => '<section class="how2-section" id="'+anchor(h)+'"><h2>'+esc(h)+'</h2>'+blocks.map(block).join('')+'</section>').join('');
 const pager = '<nav class="how2-pager" aria-label="More guides">'+(prev?'<a href="/how2s/'+prev.slug+'">← '+esc(prev.title)+'</a>':'<span></span>')+'<a href="/how2s">All guides</a>'+(next?'<a href="/how2s/'+next.slug+'">'+esc(next.title)+' →</a>':'<span></span>')+'</nav>';
 return page(g.title, g.summary, '/how2s/'+g.slug,
  '<div class="eyebrow"><a href="/how2s">Guides</a> · '+esc(HOW2_GROUPS.find(x=>x[0]===g.group)[1])+'</div><h1>'+esc(g.title)+'</h1><p class="intro">'+inline(g.summary)+'</p><p class="meta">About '+g.minutes+' minutes</p>'+sections+pager);
}
