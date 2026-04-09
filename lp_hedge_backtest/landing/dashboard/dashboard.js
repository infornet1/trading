/**
 * VIZNIAGO FURY — LP Pool Dashboard
 * Phase 1: Wallet Connect + Chain Detection
 * Phase 2: Uniswap v3 On-Chain Position Fetching
 *
 * No backend required — reads directly from public RPCs.
 */

'use strict';

// ── Chain & Contract Config ───────────────────────────────────────────────
const CHAINS = {
  42161: {
    name:        'Arbitrum One',
    rpcs: [
      'https://arb1.arbitrum.io/rpc',            // official — most reliable
      'https://rpc.ankr.com/arbitrum',            // Ankr — CORS-friendly
      'https://arbitrum.llamarpc.com',            // llamarpc fallback
      'https://arbitrum-one.public.blastapi.io',  // BlastAPI fallback
    ],
    nfpmAddr:    '0xC36442b4a4522E871399CD717aBDD847Ab11FE88',
    factoryAddr: '0x1F98431c8aD98523631AE4a59f267346ea31F984',
  },
  1: {
    name:        'Ethereum',
    rpcs: [
      'https://cloudflare-eth.com',               // Cloudflare — very stable
      'https://rpc.ankr.com/eth',                 // Ankr
      'https://eth.llamarpc.com',                 // llamarpc fallback
    ],
    nfpmAddr:    '0xC36442b4a4522E871399CD717aBDD847Ab11FE88',
    factoryAddr: '0x1F98431c8aD98523631AE4a59f267346ea31F984',
  },
  8453: {
    name:        'Base',
    rpcs: [
      'https://mainnet.base.org',                 // official Base RPC
      'https://rpc.ankr.com/base',                // Ankr
      'https://base.llamarpc.com',                // llamarpc fallback
    ],
    nfpmAddr:    '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f4',
    factoryAddr: '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',
  },
};

// ── Watch RPC Selector ────────────────────────────────────────────────────
// Tries each RPC in order, returns the first one that responds within 5 s.
async function makeWatchProvider(chainId) {
  const chainCfg = CHAINS[chainId];
  if (!chainCfg) throw new Error('Unsupported chain ' + chainId);

  let lastErr;
  for (const rpc of chainCfg.rpcs) {
    try {
      const provider = new ethers.JsonRpcProvider(rpc);
      // Race a real call against a 5 s hard timeout to confirm the endpoint works
      await Promise.race([
        provider.getBlockNumber(),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000)),
      ]);
      console.log('[RPC] Using', rpc);
      return provider;
    } catch (e) {
      console.warn('[RPC] Failed:', rpc, '—', e.message, '— trying next…');
      lastErr = e;
    }
  }
  throw new Error('All RPCs for ' + chainCfg.name + ' are unreachable. Check your connection.');
}

// ── Known Token Registry (all addresses lowercase) ────────────────────────
const KNOWN_TOKENS = {
  // Arbitrum One
  '0x82af49447d8a07e3bd95bd0d56f35241523fbab1': { symbol: 'WETH',   decimals: 18 },
  '0xaf88d065e77c8cc2239327c5edb3a432268e5831': { symbol: 'USDC',   decimals: 6  },
  '0xff970a61a04b1ca14834a43f5de4533ebddb5cc6': { symbol: 'USDC.e', decimals: 6  },
  '0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9': { symbol: 'USDT',   decimals: 6  },
  '0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f': { symbol: 'WBTC',   decimals: 8  },
  '0xda10009cbd5d07dd0cecc66161fc93d7c9000da1': { symbol: 'DAI',    decimals: 18 },
  // Ethereum mainnet
  '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': { symbol: 'WETH',   decimals: 18 },
  '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': { symbol: 'USDC',   decimals: 6  },
  '0xdac17f958d2ee523a2206206994597c13d831ec7': { symbol: 'USDT',   decimals: 6  },
  '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': { symbol: 'WBTC',   decimals: 8  },
  '0x6b175474e89094c44da98b954eedeac495271d0f': { symbol: 'DAI',    decimals: 18 },
  // Base
  '0x4200000000000000000000000000000000000006': { symbol: 'WETH',   decimals: 18 },
  '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913': { symbol: 'USDC',   decimals: 6  },
};

const STABLES = new Set(['USDC', 'USDC.e', 'USDT', 'DAI']);

// ── Minimal ABIs ──────────────────────────────────────────────────────────
const NFPM_ABI = [
  'function balanceOf(address owner) view returns (uint256)',
  'function tokenOfOwnerByIndex(address owner, uint256 index) view returns (uint256)',
  'function ownerOf(uint256 tokenId) view returns (address)',
  'function positions(uint256 tokenId) view returns (uint96 nonce, address operator, address token0, address token1, uint24 fee, int24 tickLower, int24 tickUpper, uint128 liquidity, uint256 feeGrowthInside0LastX128, uint256 feeGrowthInside1LastX128, uint128 tokensOwed0, uint128 tokensOwed1)',
];

const POOL_ABI = [
  'function slot0() view returns (uint160 sqrtPriceX96, int24 tick, uint16 observationIndex, uint16 observationCardinality, uint16 observationCardinalityNext, uint8 feeProtocol, bool unlocked)',
];

const FACTORY_ABI = [
  'function getPool(address tokenA, address tokenB, uint24 fee) view returns (address pool)',
];

// ── App State ─────────────────────────────────────────────────────────────
const state = {
  provider:   null,      // ethers.BrowserProvider (wallet) or JsonRpcProvider (watch)
  address:    null,      // connected wallet address
  chainId:    null,      // numeric chain id
  positions:  [],        // fetched position objects
  prices:     { eth: null, btc: null },
  loading:    false,
  refreshTimer:    null,
  refreshInterval: parseInt(localStorage.getItem('vf_refresh_interval') || '0', 10), // ms; 0 = off
  watchMode:  false,     // true = read-only address watch, no wallet connected
  watchNftId: null,      // NFT token ID used to initiate watch (null = wallet search)
  activeTab:  'active',  // 'active' | 'history'
};

// ── SaaS State ────────────────────────────────────────────────────────────
const API_BASE = '/trading/lp-hedge/api';

const saas = {
  jwt:            localStorage.getItem('vf_jwt') || null,
  sessionExpired: false,   // true when a prior JWT expired — bot may still be running
  bots:           {},      // nft_token_id (string) → BotConfigOut
  sockets:        {},      // config_id (number) → WebSocket
  statuses:       {},      // config_id → last event payload
  logs:           {},      // config_id → array of log line strings (max 50)
  tgLinked:       null,    // null=unknown, false=not linked, {hint:"...1234"}=linked
};
const LOG_MAX    = 200;
const LOG_TTL_MS = 72 * 60 * 60 * 1000; // 72 hours in ms

// ── localStorage log cache helpers ────────────────────────────────────────
// Stores raw bot stdout lines across page refreshes with a 72-hour TTL.
// Format: JSON array of { msg: string, ts: number (epoch ms) }

const _logKey = id => `vf_log_${id}`;

function loadLogCache(configId) {
  try {
    const raw = localStorage.getItem(_logKey(configId));
    if (!raw) return [];
    const cutoff = Date.now() - LOG_TTL_MS;
    return JSON.parse(raw).filter(e => e.ts >= cutoff);
  } catch (_) { return []; }
}

function _saveLogCache(configId, entries) {
  try {
    localStorage.setItem(_logKey(configId), JSON.stringify(entries.slice(-LOG_MAX)));
  } catch (_) {} // ignore quota errors
}

function pushLogCache(configId, msg) {
  const entries = loadLogCache(configId);
  entries.push({ msg, ts: Date.now() });
  _saveLogCache(configId, entries);
}

function clearLogCache(configId) {
  try { localStorage.removeItem(_logKey(configId)); } catch (_) {}
}
// ─────────────────────────────────────────────────────────────────────────

// Track which protection drawers are open (survive re-render)
const _drawerOpen = new Set();

// ── Price Math ────────────────────────────────────────────────────────────

/**
 * Convert a Uniswap v3 tick to a human-readable display price.
 * Returns { price, label, isInverted } where price is always
 * expressed as "USD per volatile asset" when a stablecoin is involved.
 */
function tickToDisplayPrice(tick, token0Info, token1Info) {
  // P_raw = 1.0001^tick = token1_raw / token0_raw
  // P_human = P_raw * 10^(decimals0 - decimals1) = token1 per token0 (human units)
  const pHuman = Math.pow(1.0001, tick) * Math.pow(10, token0Info.decimals - token1Info.decimals);

  const t1IsStable = STABLES.has(token1Info.symbol);
  const t0IsStable = STABLES.has(token0Info.symbol);

  if (t1IsStable) {
    // price = stablecoin per volatile = USD value of token0
    return { price: pHuman, base: token0Info.symbol, quote: token1Info.symbol, isInverted: false };
  } else if (t0IsStable) {
    // price = volatile per stablecoin → invert to get USD per volatile
    return { price: 1 / pHuman, base: token1Info.symbol, quote: token0Info.symbol, isInverted: true };
  } else {
    // Non-stable pair: show token1 per token0 as-is
    return { price: pHuman, base: token0Info.symbol, quote: token1Info.symbol, isInverted: false };
  }
}

function formatPrice(price) {
  if (!price || isNaN(price)) return '—';
  if (price >= 10000) return '$' + price.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (price >= 100)   return '$' + price.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (price >= 1)     return '$' + price.toLocaleString('en-US', { maximumFractionDigits: 4 });
  return '$' + price.toLocaleString('en-US', { maximumFractionDigits: 8 });
}

function formatTokenAmount(rawBigInt, decimals, maxDecimals = 6) {
  if (!rawBigInt) return '0';
  const val = Number(rawBigInt) / Math.pow(10, decimals);
  if (val === 0) return '0';
  if (val < 0.000001) return '< 0.000001';
  return val.toLocaleString('en-US', { maximumFractionDigits: maxDecimals });
}

function truncateAddr(addr) {
  return addr.slice(0, 6) + '…' + addr.slice(-4);
}

// ── Wallet Connect ────────────────────────────────────────────────────────

window.connectWallet = async function () {
  if (!window.ethereum) {
    document.getElementById('no-wallet-msg').style.display = 'block';
    return;
  }

  try {
    setWalletBtnLoading(true);
    state.provider = new ethers.BrowserProvider(window.ethereum);

    // Request accounts (triggers Rabby/MetaMask popup)
    await state.provider.send('eth_requestAccounts', []);

    const signer  = await state.provider.getSigner();
    state.address = await signer.getAddress();
    const network = await state.provider.getNetwork();
    state.chainId = Number(network.chainId);

    onWalletConnected();
  } catch (err) {
    console.error('Wallet connect failed:', err);
    setWalletBtnLoading(false);
    showError('Could not connect wallet: ' + (err.message || err));
  }
};

window.disconnectWallet = function () {
  clearInterval(state.refreshTimer);
  state.address   = null;
  state.chainId   = null;
  state.provider  = null;
  state.positions = [];
  state.watchMode  = false;
  state.watchNftId = null;
  state.activeTab  = 'active';
  // Close bot WebSockets on disconnect
  for (const ws of Object.values(saas.sockets)) {
    try { ws.close(); } catch (_) {}
  }
  saas.sockets  = {};
  saas.bots     = {};
  saas.statuses = {};
  saas.jwt      = null;
  localStorage.removeItem('vf_jwt');
  _drawerOpen.clear();
  updateNuclearBtn();
  renderRefreshControl();
  renderConnectPrompt();
};

// ── Tab Navigation ────────────────────────────────────────────────────────

window.setTab = function (tab) {
  state.activeTab = tab;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('tab-btn--active', btn.id === 'tab-' + tab);
  });
  const isExplore = tab === 'explore';
  document.getElementById('explore-panel')?.classList.toggle('hidden', !isExplore);
  if (!isExplore) renderPositions();
};

// ── Watch Address (read-only) ─────────────────────────────────────────────

window.startWatchMode = async function () {
  // Branch to NFT search if that mode is active
  const nftRow = document.getElementById('watch-nft-row');
  if (nftRow && !nftRow.classList.contains('hidden')) {
    return startNftSearchMode();
  }

  const input   = document.getElementById('watch-addr-input');
  const rawAddr = (input?.value || '').trim();
  if (!rawAddr) return;

  if (!ethers.isAddress(rawAddr)) {
    showError(window.t ? window.t('dash.watch.invalid') : 'Invalid address');
    return;
  }

  const addr    = ethers.getAddress(rawAddr);
  const chainId = parseInt(document.getElementById('watch-chain-select').value, 10);
  if (!CHAINS[chainId]) return;

  const watchBtn  = document.querySelector('.watch-card .btn-active');
  const watchSpan = watchBtn?.querySelector('span');
  if (watchBtn)  { watchBtn.disabled = true; watchBtn.style.opacity = '0.6'; }
  if (watchSpan) { watchSpan.textContent = '…'; }

  let provider;
  try {
    provider = await makeWatchProvider(chainId);
  } catch (e) {
    showError(e.message);
    if (watchBtn)  { watchBtn.disabled = false; watchBtn.style.opacity = ''; }
    if (watchSpan) { watchSpan.textContent = window.t ? window.t('dash.watch.btn') : 'Watch'; }
    return;
  }

  if (watchBtn)  { watchBtn.disabled = false; watchBtn.style.opacity = ''; }
  if (watchSpan) { watchSpan.textContent = window.t ? window.t('dash.watch.btn') : 'Watch'; }

  state.watchMode  = true;
  state.watchNftId = null;
  state.address    = addr;
  state.chainId    = chainId;
  state.provider   = provider;

  hide('connect-prompt');
  show('dashboard-content');
  updateWalletBar();
  updateChainPills();
  fetchLivePrices();
  fetchPositions();
  applyRefreshInterval();
  renderRefreshControl();
};

async function startNftSearchMode() {
  const input   = document.getElementById('watch-nft-input');
  const rawId   = (input?.value || '').trim().replace(/^#/, '');
  if (!rawId || isNaN(rawId) || rawId === '') {
    showError('Ingresa un token ID válido (número entero)');
    return;
  }

  const chainId = parseInt(document.getElementById('watch-nft-chain-select').value, 10);
  if (!CHAINS[chainId]) return;

  const watchBtn  = document.querySelector('#watch-nft-row .btn');
  const watchSpan = watchBtn?.querySelector('span');
  if (watchBtn)  { watchBtn.disabled = true; watchBtn.style.opacity = '0.6'; }
  if (watchSpan) { watchSpan.textContent = '…'; }

  let provider;
  try {
    provider = await makeWatchProvider(chainId);
  } catch (e) {
    showError(e.message);
    if (watchBtn)  { watchBtn.disabled = false; watchBtn.style.opacity = ''; }
    if (watchSpan) { watchSpan.textContent = window.t ? window.t('dash.watch.btn') : 'Watch'; }
    return;
  }

  let owner;
  try {
    const nfpm = new ethers.Contract(CHAINS[chainId].nfpmAddr, NFPM_ABI, provider);
    owner = await nfpm.ownerOf(BigInt(rawId));
  } catch (e) {
    showError('NFT no encontrado en esta red. Verifica el ID y la red seleccionada.');
    if (watchBtn)  { watchBtn.disabled = false; watchBtn.style.opacity = ''; }
    if (watchSpan) { watchSpan.textContent = window.t ? window.t('dash.watch.btn') : 'Watch'; }
    return;
  }

  if (watchBtn)  { watchBtn.disabled = false; watchBtn.style.opacity = ''; }
  if (watchSpan) { watchSpan.textContent = window.t ? window.t('dash.watch.btn') : 'Watch'; }

  state.watchMode  = true;
  state.watchNftId = rawId;
  state.address    = owner;
  state.chainId    = chainId;
  state.provider   = provider;

  hide('connect-prompt');
  show('dashboard-content');
  updateWalletBar();
  updateChainPills();
  fetchLivePrices();
  fetchPositions();
  applyRefreshInterval();
  renderRefreshControl();
}

window.switchWatchMode = function (mode) {
  const walletRow = document.getElementById('watch-wallet-row');
  const nftRow    = document.getElementById('watch-nft-row');
  const nftNote   = document.getElementById('watch-nft-note');
  document.querySelectorAll('.watch-mode-pill').forEach(p =>
    p.classList.toggle('watch-mode-pill--active', p.dataset.mode === mode)
  );
  walletRow?.classList.toggle('hidden', mode !== 'wallet');
  nftRow?.classList.toggle('hidden', mode !== 'nft');
  nftNote?.classList.toggle('hidden', mode !== 'nft');
};

// ── Explore Tab ───────────────────────────────────────────────────────────

window.switchExploreMode = function (mode) {
  document.querySelectorAll('#explore-panel .watch-mode-pill').forEach(p =>
    p.classList.toggle('watch-mode-pill--active', p.dataset.mode === mode)
  );
  document.getElementById('explore-wallet-row')?.classList.toggle('hidden', mode !== 'wallet');
  document.getElementById('explore-nft-row')?.classList.toggle('hidden', mode !== 'nft');
  document.getElementById('explore-nft-note')?.classList.toggle('hidden', mode !== 'nft');
};

window.exploreSearch = async function () {
  const isNft = !document.getElementById('explore-nft-row')?.classList.contains('hidden');
  let address, chainId, provider, nftId = null;

  // Show loading state
  show('explore-loading');
  hide('explore-empty');
  hide('explore-owner-bar');
  document.getElementById('explore-results').innerHTML = '';

  if (isNft) {
    const rawId = (document.getElementById('explore-nft-input')?.value || '').trim().replace(/^#/, '');
    if (!rawId || isNaN(rawId)) {
      hide('explore-loading');
      showError('Ingresa un token ID válido (número entero)');
      return;
    }
    chainId = parseInt(document.getElementById('explore-nft-chain-select').value, 10);
    if (!CHAINS[chainId]) { hide('explore-loading'); return; }
    try {
      provider = await makeWatchProvider(chainId);
    } catch (e) { hide('explore-loading'); showError(e.message); return; }
    try {
      const nfpm = new ethers.Contract(CHAINS[chainId].nfpmAddr, NFPM_ABI, provider);
      address = await nfpm.ownerOf(BigInt(rawId));
      nftId   = rawId;
    } catch (_) {
      hide('explore-loading');
      showError('NFT no encontrado en esta red. Verifica el ID y la red seleccionada.');
      return;
    }
  } else {
    const rawAddr = (document.getElementById('explore-addr-input')?.value || '').trim();
    if (!rawAddr) { hide('explore-loading'); return; }
    if (!ethers.isAddress(rawAddr)) {
      hide('explore-loading');
      showError(window.t ? window.t('dash.watch.invalid') : 'Invalid address');
      return;
    }
    address = ethers.getAddress(rawAddr);
    chainId = parseInt(document.getElementById('explore-chain-select').value, 10);
    if (!CHAINS[chainId]) { hide('explore-loading'); return; }
    try {
      provider = await makeWatchProvider(chainId);
    } catch (e) { hide('explore-loading'); showError(e.message); return; }
  }

  await lookupPositions(address, chainId, provider, nftId);
};

async function lookupPositions(address, chainId, provider, nftId) {
  const chainCfg  = CHAINS[chainId];
  const resultsEl = document.getElementById('explore-results');
  if (!resultsEl) return;

  try {
    const nfpm    = new ethers.Contract(chainCfg.nfpmAddr, NFPM_ABI, provider);
    const balance = Number(await nfpm.balanceOf(address));

    hide('explore-loading');

    if (balance === 0) { show('explore-empty'); return; }

    const tokenIds = await Promise.all(
      Array.from({ length: balance }, (_, i) => nfpm.tokenOfOwnerByIndex(address, i))
    );

    const rawPositions = await Promise.all(
      tokenIds.map(id => nfpm.positions(id).then(p => ({
        tokenId:     id,
        token0:      p.token0,
        token1:      p.token1,
        fee:         p.fee,
        tickLower:   p.tickLower,
        tickUpper:   p.tickUpper,
        liquidity:   p.liquidity,
        tokensOwed0: p.tokensOwed0,
        tokensOwed1: p.tokensOwed1,
      })))
    );

    const uniquePools = new Map();
    const factory = new ethers.Contract(chainCfg.factoryAddr, FACTORY_ABI, provider);
    for (const pos of rawPositions) {
      const key = `${pos.token0.toLowerCase()}-${pos.token1.toLowerCase()}-${pos.fee}`;
      if (!uniquePools.has(key))
        uniquePools.set(key, { token0: pos.token0, token1: pos.token1, fee: Number(pos.fee), slot0: null });
    }
    await Promise.all(Array.from(uniquePools.entries()).map(async ([key, pool]) => {
      try {
        const addr = await factory.getPool(pool.token0, pool.token1, pool.fee);
        if (addr === '0x0000000000000000000000000000000000000000') return;
        const slot0 = await new ethers.Contract(addr, POOL_ABI, provider).slot0();
        uniquePools.get(key).slot0        = { sqrtPriceX96: slot0[0], tick: Number(slot0[1]) };
        uniquePools.get(key).poolAddress  = addr.toLowerCase();
      } catch (_) {}
    }));

    const positions = rawPositions.map(raw => {
      const key        = `${raw.token0.toLowerCase()}-${raw.token1.toLowerCase()}-${Number(raw.fee)}`;
      const pool       = uniquePools.get(key);
      const token0Info = KNOWN_TOKENS[raw.token0.toLowerCase()] || { symbol: raw.token0.slice(0,6)+'…', decimals: 18 };
      const token1Info = KNOWN_TOKENS[raw.token1.toLowerCase()] || { symbol: raw.token1.slice(0,6)+'…', decimals: 18 };
      const tickLower   = Number(raw.tickLower);
      const tickUpper   = Number(raw.tickUpper);
      const currentTick = pool?.slot0?.tick ?? null;
      const liquidity   = BigInt(raw.liquidity.toString());
      const tokensOwed0 = BigInt(raw.tokensOwed0.toString());
      const tokensOwed1 = BigInt(raw.tokensOwed1.toString());
      const priceLowerObj   = tickToDisplayPrice(tickLower,   token0Info, token1Info);
      const priceUpperObj   = tickToDisplayPrice(tickUpper,   token0Info, token1Info);
      const priceCurrentObj = currentTick !== null ? tickToDisplayPrice(currentTick, token0Info, token1Info) : null;
      let priceLower   = priceLowerObj.price;
      let priceUpper   = priceUpperObj.price;
      let priceCurrent = priceCurrentObj?.price ?? null;
      if (priceLower > priceUpper) [priceLower, priceUpper] = [priceUpper, priceLower];
      let rangeStatus = 'unknown';
      if (currentTick !== null) {
        if (liquidity === 0n)             rangeStatus = 'closed';
        else if (currentTick < tickLower) rangeStatus = 'out-low';
        else if (currentTick > tickUpper) rangeStatus = 'out-high';
        else                              rangeStatus = 'in-range';
      }
      let rangePercent = null;
      if (priceCurrent !== null && priceUpper > priceLower) {
        rangePercent = Math.max(0, Math.min(100,
          (priceCurrent - priceLower) / (priceUpper - priceLower) * 100
        ));
      }
      return {
        tokenId:      raw.tokenId.toString(),
        token0:       raw.token0,
        token1:       raw.token1,
        fee:          Number(raw.fee),
        token0Info,   token1Info,
        tickLower,    tickUpper,
        priceLower,   priceUpper,  priceCurrent,
        priceBase:    priceLowerObj.base,
        priceQuote:   priceLowerObj.quote,
        rangeStatus,  rangePercent,
        liquidity,    tokensOwed0, tokensOwed1,
        sqrtPriceX96: pool?.slot0?.sqrtPriceX96 ?? null,
        poolAddress:  pool?.poolAddress ?? null,
        _exploreOnly: true,
      };
    });

    const order = { 'in-range':0, 'out-low':1, 'out-high':2, 'closed':3, 'unknown':4 };
    positions.sort((a, b) => (order[a.rangeStatus] ?? 4) - (order[b.rangeStatus] ?? 4));
    positions.forEach(pos => resultsEl.appendChild(buildPositionCard(pos)));
    positions.forEach(pos => loadPositionAPR(pos));

    // Update owner bar
    const ownerAddrEl = document.getElementById('explore-owner-addr');
    if (ownerAddrEl) ownerAddrEl.textContent = truncateAddr(address);
    const nftTagEl = document.getElementById('explore-owner-nft');
    if (nftTagEl) {
      nftTagEl.textContent = nftId ? `NFT #${nftId}` : '';
      nftTagEl.classList.toggle('hidden', !nftId);
    }
    show('explore-owner-bar');

  } catch (e) {
    hide('explore-loading');
    showError('Error al buscar posiciones: ' + (e.message || e));
  }
}

window.clearExplore = function () {
  document.getElementById('explore-results').innerHTML = '';
  if (document.getElementById('explore-addr-input'))
    document.getElementById('explore-addr-input').value = '';
  if (document.getElementById('explore-nft-input'))
    document.getElementById('explore-nft-input').value = '';
  hide('explore-owner-bar');
  hide('explore-empty');
};

window.refreshAll = async function () {
  const btn = document.querySelector('.ticker-refresh-btn');
  if (btn) btn.classList.add('spinning');
  await Promise.all([fetchLivePrices(), fetchPositions()]);
  if (btn) btn.classList.remove('spinning');
};

function registerWalletListeners() {
  // Remove before re-adding to prevent listener stacking on reconnect
  window.ethereum.removeListener('accountsChanged', handleAccountsChanged);
  window.ethereum.removeListener('chainChanged',    handleChainChanged);
  window.ethereum.on('accountsChanged', handleAccountsChanged);
  window.ethereum.on('chainChanged',    handleChainChanged);
}

async function onWalletConnected() {
  setWalletBtnLoading(false);
  renderWalletConnected();

  registerWalletListeners();

  // Load bots FIRST (if JWT exists) so protection drawers render correct
  // state on first paint — avoids the "activate bot" flash on tab return.
  updateNuclearBtn();
  await saasLoadBots();
  updateWalletDropdown();

  // Check maintenance flag and show banner if active
  checkMaintenanceStatus();

  // Initial data load (positions rendered after bots are known)
  fetchLivePrices();
  fetchPositions();

  applyRefreshInterval();
  renderRefreshControl();
}

function handleAccountsChanged(accounts) {
  if (!accounts.length) {
    disconnectWallet();
    return;
  }
  state.address = accounts[0];
  updateWalletBar();
  fetchPositions();
}

function handleChainChanged(chainIdHex) {
  state.chainId = parseInt(chainIdHex, 16);
  // Brief delay — some wallets (Rabby, MetaMask) are still finalising the
  // chain switch when this event fires; recreating the provider immediately
  // can result in calls going to the old chain.
  setTimeout(() => {
    state.provider = new ethers.BrowserProvider(window.ethereum);
    updateWalletBar();
    updateChainPills();
    fetchPositions();
  }, 150);
}

// ── Network Switcher ──────────────────────────────────────────────────────

window.switchToChain = async function (chainIdHex) {
  const chainId  = parseInt(chainIdHex, 16);
  const chainCfg = CHAINS[chainId];

  // Watch mode: probe fallback RPCs and switch directly — no wallet involved
  if (state.watchMode) {
    if (!chainCfg) return;
    try {
      const provider   = await makeWatchProvider(chainId);
      state.chainId    = chainId;
      state.provider   = provider;
    } catch (e) {
      showError(e.message);
      return;
    }
    updateWalletBar();
    updateChainPills();
    fetchPositions();
    return;
  }

  if (!window.ethereum) return;
  try {
    await window.ethereum.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: chainIdHex }],
    });
    // chainChanged event will fire and trigger handleChainChanged automatically
  } catch (err) {
    if (err.code === 4902) {
      showError('This chain is not added to your wallet yet. Add it in Rabby first.');
    } else if (err.code !== 4001) {
      // 4001 = user rejected — silently ignore
      showError('Failed to switch network: ' + (err.message || err));
    }
  }
};

// ── On-Chain Position Fetching ────────────────────────────────────────────

async function fetchPositions() {
  if (!state.address || !state.provider) return;

  const chainCfg = CHAINS[state.chainId];

  show('positions-loading');
  hide('no-positions');
  document.getElementById('positions-grid').innerHTML = '';

  if (!chainCfg) {
    hide('positions-loading');
    updateWrongNetworkBanner(true);
    updatePositionCount(0);
    return;
  }

  updateWrongNetworkBanner(false);

  try {
    // Use the wallet's own provider — it is already connected to the correct chain
    // (JsonRpcProvider constructor is lazy and never throws, so the old try/catch
    //  fallback never triggered; wallet provider avoids that race entirely)
    const readProvider = state.provider;

    const nfpm = new ethers.Contract(chainCfg.nfpmAddr, NFPM_ABI, readProvider);

    // How many LP NFTs does this wallet own?
    const balance = Number(await nfpm.balanceOf(state.address));

    if (balance === 0) {
      state.positions = [];
      hide('positions-loading');
      renderPositions();
      return;
    }

    // Fetch all tokenIds in parallel
    const tokenIdPromises = [];
    for (let i = 0; i < balance; i++) {
      tokenIdPromises.push(nfpm.tokenOfOwnerByIndex(state.address, i));
    }
    const tokenIds = await Promise.all(tokenIdPromises);

    // Fetch position data for each tokenId in parallel.
    // NOTE: ethers v6 returns a Result (Proxy) object — named properties are
    // NOT enumerable so { ...p } only copies numeric indices, not token0/token1.
    // Must extract fields explicitly.
    const posDataPromises = tokenIds.map(id => nfpm.positions(id).then(p => ({
      tokenId:     id,
      token0:      p.token0,
      token1:      p.token1,
      fee:         p.fee,
      tickLower:   p.tickLower,
      tickUpper:   p.tickUpper,
      liquidity:   p.liquidity,
      tokensOwed0: p.tokensOwed0,
      tokensOwed1: p.tokensOwed1,
    })));
    const rawPositions = await Promise.all(posDataPromises);

    // Filter out closed (zero-liquidity) positions — keep but tag them
    // then fetch pool slot0 for unique pools
    const uniquePools = new Map(); // key: `${token0}-${token1}-${fee}` → { token0, token1, fee, slot0 }

    const factory = new ethers.Contract(chainCfg.factoryAddr, FACTORY_ABI, readProvider);

    // Collect unique pool keys
    for (const pos of rawPositions) {
      const key = `${pos.token0.toLowerCase()}-${pos.token1.toLowerCase()}-${pos.fee}`;
      if (!uniquePools.has(key)) {
        uniquePools.set(key, { token0: pos.token0, token1: pos.token1, fee: Number(pos.fee), slot0: null });
      }
    }

    // Fetch pool addresses & slot0 in parallel
    const poolFetches = Array.from(uniquePools.entries()).map(async ([key, pool]) => {
      try {
        const poolAddr = await factory.getPool(pool.token0, pool.token1, pool.fee);
        if (poolAddr === '0x0000000000000000000000000000000000000000') return;
        const poolContract = new ethers.Contract(poolAddr, POOL_ABI, readProvider);
        const slot0 = await poolContract.slot0();
        uniquePools.get(key).slot0      = { sqrtPriceX96: slot0[0], tick: Number(slot0[1]) };
        uniquePools.get(key).poolAddress = poolAddr.toLowerCase();
      } catch (err) {
        console.warn(`Could not fetch pool slot0 for key ${key}:`, err.message);
      }
    });
    await Promise.all(poolFetches);

    // Build final position objects
    state.positions = rawPositions.map(raw => {
      const key = `${raw.token0.toLowerCase()}-${raw.token1.toLowerCase()}-${Number(raw.fee)}`;
      const pool = uniquePools.get(key);

      const token0Info = KNOWN_TOKENS[raw.token0.toLowerCase()] || { symbol: raw.token0.slice(0, 6) + '…', decimals: 18 };
      const token1Info = KNOWN_TOKENS[raw.token1.toLowerCase()] || { symbol: raw.token1.slice(0, 6) + '…', decimals: 18 };

      const tickLower   = Number(raw.tickLower);
      const tickUpper   = Number(raw.tickUpper);
      const currentTick = pool?.slot0?.tick ?? null;
      const liquidity   = BigInt(raw.liquidity.toString());
      const tokensOwed0 = BigInt(raw.tokensOwed0.toString());
      const tokensOwed1 = BigInt(raw.tokensOwed1.toString());

      // Price display (account for token ordering)
      const priceLowerObj   = tickToDisplayPrice(tickLower,   token0Info, token1Info);
      const priceUpperObj   = tickToDisplayPrice(tickUpper,   token0Info, token1Info);
      const priceCurrentObj = currentTick !== null ? tickToDisplayPrice(currentTick, token0Info, token1Info) : null;

      // When isInverted (token0 is stable), lower tick = higher display price
      let priceLower   = priceLowerObj.price;
      let priceUpper   = priceUpperObj.price;
      let priceCurrent = priceCurrentObj?.price ?? null;

      // Ensure lower < upper in display terms
      if (priceLower > priceUpper) {
        [priceLower, priceUpper] = [priceUpper, priceLower];
      }

      // Range status
      let rangeStatus = 'unknown';
      if (currentTick !== null) {
        if (liquidity === 0n)          rangeStatus = 'closed';
        else if (currentTick < tickLower)  rangeStatus = 'out-low';
        else if (currentTick > tickUpper)  rangeStatus = 'out-high';
        else                               rangeStatus = 'in-range';
      }

      // % through the range (0–100 clamped)
      let rangePercent = null;
      if (priceCurrent !== null && priceUpper > priceLower) {
        rangePercent = Math.max(0, Math.min(100,
          (priceCurrent - priceLower) / (priceUpper - priceLower) * 100
        ));
      }

      return {
        tokenId:      raw.tokenId.toString(),
        token0:       raw.token0,
        token1:       raw.token1,
        fee:          Number(raw.fee),
        token0Info,
        token1Info,
        tickLower,
        tickUpper,
        liquidity,
        tokensOwed0,
        tokensOwed1,
        sqrtPriceX96: pool?.slot0?.sqrtPriceX96 ?? null,
        poolAddress:  pool?.poolAddress ?? null,
        priceLower,
        priceUpper,
        priceCurrent,
        priceBase:    priceLowerObj.base,
        priceQuote:   priceLowerObj.quote,
        rangeStatus,
        rangePercent,
      };
    });

    hide('positions-loading');
    renderPositions();

  } catch (err) {
    console.error('fetchPositions error:', err);
    hide('positions-loading');
    showError('Failed to load positions: ' + (err.message || err));
  }
}

// ── Live Price Ticker ─────────────────────────────────────────────────────

async function fetchLivePrices() {
  try {
    const res = await fetch(API_BASE + '/prices', { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error('Price API HTTP ' + res.status);
    const data = await res.json();
    state.prices.eth = data?.ethereum?.usd ?? null;
    state.prices.btc = data?.bitcoin?.usd   ?? null;
  } catch (err) {
    console.warn('Price fetch failed:', err.message);
    // Silently fail — ticker will show last known value
  }
  renderPriceTicker();
}

// ── Render ────────────────────────────────────────────────────────────────

function renderConnectPrompt() {
  hide('dashboard-content');
  show('connect-prompt');

  const btn = document.getElementById('wallet-btn');
  btn.textContent = window.t ? window.t('dash.btn.connect') : '🟢 Connect Wallet';
  btn.onclick = connectWallet;

  const chainBadge = document.getElementById('chain-badge');
  chainBadge.classList.add('hidden');
}

function renderWalletConnected() {
  hide('connect-prompt');
  show('dashboard-content');
  updateWalletBar();
}

function updateWalletBar() {
  const t = window.t || (k => k);
  document.getElementById('ws-address').textContent = truncateAddr(state.address);
  const chainCfg = CHAINS[state.chainId];
  document.getElementById('ws-chain').textContent = chainCfg
    ? chainCfg.name
    : `Chain ID ${state.chainId} (unsupported)`;

  // Watch mode badge in summary bar
  const watchBadge = document.getElementById('watch-badge');
  if (watchBadge) {
    watchBadge.classList.toggle('hidden', !state.watchMode);
    if (state.watchMode) watchBadge.textContent = t('dash.watch.badge');
  }

  // Disconnect button label
  const disconnectLabel = document.getElementById('disconnect-label');
  if (disconnectLabel) {
    disconnectLabel.textContent = state.watchMode
      ? t('dash.watch.stop')
      : t('dash.ws.disconnect');
  }

  // Navbar wallet button → shows address + dropdown toggle (eye prefix in watch mode)
  const btn = document.getElementById('wallet-btn');
  btn.textContent = (state.watchMode ? '👁 ' : '🟢 ') + truncateAddr(state.address) + ' ▾';
  btn.classList.toggle('btn--watch-mode', state.watchMode);
  btn.onclick = toggleWalletDropdown;

  // Watch-mode banner — prominent amber bar, shown only in watch mode
  const watchBanner = document.getElementById('watch-mode-banner');
  if (watchBanner) {
    watchBanner.classList.toggle('hidden', !state.watchMode);
    const addrEl = document.getElementById('watch-mode-addr');
    if (addrEl) addrEl.textContent = state.watchNftId
      ? `NFT #${state.watchNftId} · ${truncateAddr(state.address)}`
      : truncateAddr(state.address);
  }

  // Chain badge in navbar
  const badge = document.getElementById('chain-badge');
  badge.classList.remove('hidden', 'chain-wrong');
  if (chainCfg) {
    badge.textContent = chainCfg.name;
  } else {
    badge.textContent = 'Wrong Network';
    badge.classList.add('chain-wrong');
  }

  updateChainPills();
}

function updateChainPills() {
  // Highlight the active chain pill; grey-out the others
  const pillMap = { 42161: 'pill-42161', 1: 'pill-1', 8453: 'pill-8453' };
  Object.entries(pillMap).forEach(([id, elId]) => {
    const el = document.getElementById(elId);
    if (!el) return;
    el.classList.toggle('chain-pill--active', Number(id) === state.chainId);
  });
}

// ── Wallet Dropdown ───────────────────────────────────────────────────────

function toggleWalletDropdown() {
  const menu = document.getElementById('wallet-dropdown-menu');
  if (!menu) return;
  menu.classList.contains('hidden') ? openWalletDropdown() : closeWalletDropdown();
}

function openWalletDropdown() {
  const menu = document.getElementById('wallet-dropdown-menu');
  if (!menu) return;
  menu.innerHTML = buildWalletDropdownContent();
  menu.classList.remove('hidden');
  // Fetch HL balance async if not yet cached, then refresh dropdown content
  if (!_hlBalanceCache && saas.jwt) {
    fetchHLBalance().then(() => {
      if (!menu.classList.contains('hidden')) {
        menu.innerHTML = buildWalletDropdownContent();
      }
    });
  }
}

function closeWalletDropdown() {
  const menu = document.getElementById('wallet-dropdown-menu');
  if (menu) menu.classList.add('hidden');
}

// Call this after bot status updates to keep dropdown fresh if open
function updateWalletDropdown() {
  const menu = document.getElementById('wallet-dropdown-menu');
  if (menu && !menu.classList.contains('hidden')) {
    menu.innerHTML = buildWalletDropdownContent();
  }
}

function buildWalletDropdownContent() {
  const chain  = CHAINS[state.chainId];
  const bots   = Object.values(saas.bots);
  const hl     = _hlBalanceCache;
  const lpActiveCount   = document.getElementById('tab-count-active')?.textContent  || '—';
  const lpHistoryCount  = document.getElementById('tab-count-history')?.textContent || '—';

  // ── Header ─────────────────────────────────────────────────────────────
  let html = `
    <div class="wd-header">
      <div class="wd-address-row">
        <span class="wd-address">${truncateAddr(state.address)}</span>
        <button class="wd-copy-btn" onclick="navigator.clipboard.writeText('${state.address}');this.textContent='✓';setTimeout(()=>this.textContent='⎘',1500)" title="Copy full address">⎘</button>
      </div>
      <div class="wd-chain-label">${chain ? chain.name : 'Unknown Network'}</div>
    </div>`;

  // ── Hyperliquid Balance ─────────────────────────────────────────────────
  html += `<div class="wd-section">
    <div class="wd-section-title">HYPERLIQUID</div>`;
  if (hl) {
    const av  = Number(hl.account_value  || 0).toFixed(2);
    const wd  = Number(hl.withdrawable   || 0).toFixed(2);
    const pos = Number(hl.total_notional_position || 0).toFixed(2);
    html += `
      <div class="wd-kv-row"><span class="wd-kv-label">Account Value</span><span class="wd-kv-value">$${av}</span></div>
      <div class="wd-kv-row"><span class="wd-kv-label">Withdrawable</span><span class="wd-kv-value">$${wd}</span></div>
      <div class="wd-kv-row"><span class="wd-kv-label">Open Notional</span><span class="wd-kv-value">$${pos}</span></div>`;
  } else if (saas.jwt) {
    html += `<div class="wd-loading-row">Fetching balance…</div>`;
  } else {
    html += `<div class="wd-loading-row">Sign in to view</div>`;
  }
  html += `</div>`;

  // ── Bot Protection ──────────────────────────────────────────────────────
  html += `<div class="wd-section">
    <div class="wd-section-title">BOT PROTECTION${bots.length ? ` <span class="wd-count-badge">${bots.length}</span>` : ''}</div>`;

  if (!saas.jwt) {
    html += `<div class="wd-loading-row">Sign in with wallet to manage bots</div>`;
  } else if (!bots.length) {
    html += `<div class="wd-loading-row">No bots configured</div>`;
  } else {
    const modeLabel = m => m === 'aragan' ? 'Defensor Bajista'
                         : m === 'avaro'  ? 'Defensor Alcista'
                         : m === 'fury'   ? 'FURY RSI'
                         : m === 'whale'  ? 'WHALE Tracker'
                         : m;
    bots.forEach(bot => {
      const lastEvt  = saas.statuses[bot.id];
      const isActive = bot.active;
      const isPaper  = bot.paper_trade;
      const statusLabel = isActive ? (isPaper ? 'PAPER' : 'LIVE') : 'INACTIVE';
      const statusClass = isActive ? (isPaper ? 'wd-status-paper' : 'wd-status-live') : 'wd-status-off';

      let evtHtml = '';
      if (lastEvt && isActive) {
        const raw   = (lastEvt.event || lastEvt.event_type || '').replace(/_/g, ' ').toUpperCase();
        const price = lastEvt.price != null ? ` @ $${Number(lastEvt.price).toFixed(2)}` : '';
        const pnlN  = lastEvt.pnl  != null ? Number(lastEvt.pnl) : null;
        const pnlStr = pnlN != null
          ? `<span class="${pnlN >= 0 ? 'wd-pnl-pos' : 'wd-pnl-neg'}">${pnlN >= 0 ? '+' : ''}$${Math.abs(pnlN).toFixed(2)}</span>`
          : '';
        evtHtml = `<div class="wd-bot-evt">${raw}${price}${pnlStr ? ' · ' + pnlStr : ''}</div>`;
      }

      html += `
        <div class="wd-bot-row">
          <div class="wd-bot-top">
            <span class="wd-bot-nft">NFT #${bot.nft_token_id}</span>
            <span class="wd-bot-status ${statusClass}">${statusLabel}</span>
          </div>
          <div class="wd-bot-mode">${modeLabel(bot.mode)}${bot.target_leverage ? ' · ' + bot.target_leverage + 'x' : ''}</div>
          ${evtHtml}
        </div>`;
    });
  }
  html += `</div>`;

  // ── Telegram Alerts ─────────────────────────────────────────────────────
  html += `<div class="wd-section">
    <div class="wd-section-title">TELEGRAM ALERTS</div>`;
  if (!saas.jwt) {
    html += `<div class="wd-loading-row">Sign in to link Telegram</div>`;
  } else if (saas.tgLinked && saas.tgLinked.count) {
    const n = saas.tgLinked.count;
    html += `<div class="wd-tg-linked">
      <span class="wd-tg-check">✓</span> @vizniago_bot — ${n} wallet${n > 1 ? 's' : ''} linked
    </div>`;
  } else {
    const walletArg = state.address ? state.address.toLowerCase() : '0x…';
    const cmd = `/start ${walletArg}`;
    html += `<div class="wd-tg-setup">
      <div class="wd-tg-step">Open <a href="https://t.me/vizniago_bot" target="_blank" rel="noopener" class="wd-tg-link">@vizniago_bot</a> and send:</div>
      <div class="wd-tg-cmd" data-cmd="${cmd}" onclick="copyTgCmd(this)">${cmd}</div>
      <div class="wd-tg-copy-hint">Tap to copy</div>
    </div>`;
  }
  html += `</div>`;

  // ── LP Positions summary ────────────────────────────────────────────────
  html += `
    <div class="wd-section">
      <div class="wd-section-title">LP POSITIONS</div>
      <div class="wd-kv-row">
        <span class="wd-kv-label">Active</span><span class="wd-kv-value">${lpActiveCount}</span>
      </div>
      <div class="wd-kv-row">
        <span class="wd-kv-label">History</span><span class="wd-kv-value">${lpHistoryCount}</span>
      </div>
    </div>`;

  // ── Footer ──────────────────────────────────────────────────────────────
  html += `
    <div class="wd-footer">
      <button class="wd-disconnect-btn" onclick="closeWalletDropdown();disconnectWallet();">
        ${state.watchMode ? 'Stop Watching' : 'Disconnect'}
      </button>
    </div>`;

  return html;
}

// ── Auto-refresh control ──────────────────────────────────────────────────

const REFRESH_OPTIONS = [
  { label: 'Off',  value: 0 },
  { label: '1m',   value: 60_000 },
  { label: '3m',   value: 180_000 },
  { label: '5m',   value: 300_000 },
  { label: '10m',  value: 600_000 },
];

function applyRefreshInterval() {
  clearInterval(state.refreshTimer);
  state.refreshTimer = null;
  if (state.refreshInterval > 0) {
    state.refreshTimer = setInterval(() => {
      fetchLivePrices();
      fetchPositions();
    }, state.refreshInterval);
  }
}

function renderRefreshControl() {
  const el = document.getElementById('refresh-control');
  if (!el) return;
  const active = state.address !== null;
  if (!active) { el.classList.add('hidden'); return; }
  el.classList.remove('hidden');

  const cur = state.refreshInterval;
  el.innerHTML = `
    <span class="refresh-label" data-i18n="dash.refresh.label">Auto</span>
    <div class="refresh-opts">
      ${REFRESH_OPTIONS.map(o => `
        <button class="refresh-opt${o.value === cur ? ' refresh-opt--active' : ''}"
                onclick="setRefreshInterval(${o.value})">${o.label}</button>
      `).join('')}
    </div>`;
}

window.setRefreshInterval = function (ms) {
  state.refreshInterval = ms;
  localStorage.setItem('vf_refresh_interval', String(ms));
  applyRefreshInterval();
  renderRefreshControl();
};

function updateTabCounts() {
  const t = window.t || (k => k);
  const activeN  = state.positions.filter(p => p.rangeStatus !== 'closed').length;
  const historyN = state.positions.filter(p => p.rangeStatus === 'closed').length;

  const elA = document.getElementById('tab-count-active');
  const elH = document.getElementById('tab-count-history');
  if (elA) elA.textContent = activeN;
  if (elH) elH.textContent = historyN;

  // ws-count reflects the currently visible tab
  const n = state.activeTab === 'history' ? historyN : activeN;
  const word = t(n === 1 ? 'dash.count.one' : 'dash.count.many');
  const wsCount = document.getElementById('ws-count');
  if (wsCount) wsCount.textContent = n + ' ' + word;
}

function updateWrongNetworkBanner(show_) {
  const el = document.getElementById('wrong-network-warning');
  if (show_) {
    el.classList.remove('hidden');
    document.getElementById('wrong-chain-name').textContent =
      CHAINS[state.chainId]?.name || `ID ${state.chainId}`;
  } else {
    el.classList.add('hidden');
  }
}

function renderPriceTicker() {
  const ethEl = document.getElementById('price-eth');
  const btcEl = document.getElementById('price-btc');
  const upEl  = document.getElementById('ticker-updated');

  ethEl.textContent = state.prices.eth ? formatPrice(state.prices.eth) : '—';
  btcEl.textContent = state.prices.btc ? formatPrice(state.prices.btc) : '—';

  const now = new Date();
  upEl.textContent = `Updated ${now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
}

function renderPositions() {
  if (state.activeTab === 'explore') return;
  const grid = document.getElementById('positions-grid');
  grid.innerHTML = '';

  // Always update counts first (affects both tabs and ws-count)
  updateTabCounts();

  hide('no-positions');
  hide('no-history');

  const isHistory = state.activeTab === 'history';
  const filtered  = state.positions.filter(p =>
    isHistory ? p.rangeStatus === 'closed' : p.rangeStatus !== 'closed'
  );

  if (!filtered.length) {
    show(isHistory ? 'no-history' : 'no-positions');
    return;
  }

  // Sort: in-range → out-low → out-high → closed → unknown
  const order = { 'in-range': 0, 'out-low': 1, 'out-high': 2, 'closed': 3, 'unknown': 4 };
  const sorted = [...filtered].sort((a, b) => (order[a.rangeStatus] ?? 4) - (order[b.rangeStatus] ?? 4));

  sorted.forEach(pos => grid.appendChild(buildPositionCard(pos)));
  // Load event history for each position (no-op if no bot configured or not authed)
  sorted.forEach(pos => loadPositionEvents(pos.tokenId));
  // Load fee APR + projections for each position (M2-1/M2-2)
  sorted.forEach(pos => loadPositionAPR(pos));
}

// ── Pool Fee APR (M2-1 / M2-2) ───────────────────────────────────────────

const GT_NETWORK = { 42161: 'arbitrum', 1: 'eth', 8453: 'base' };
// Cache keyed by pool address so we don't hammer GeckoTerminal on re-renders
const _aprCache = {};

function computeUniV3PoolAddress(chainId, token0Addr, token1Addr, fee) {
  try {
    const factory = CHAINS[chainId]?.factoryAddr;
    if (!factory) return null;
    const [t0, t1] = token0Addr.toLowerCase() < token1Addr.toLowerCase()
      ? [token0Addr, token1Addr] : [token1Addr, token0Addr];
    const INIT_HASH = '0xe34f199b19b2b4f47f68442619d555527d244f78a3297ea89325f843f87b8b54';
    const salt = ethers.solidityPackedKeccak256(['address', 'address', 'uint24'], [t0, t1, fee]);
    return ethers.getCreate2Address(factory, salt, INIT_HASH);
  } catch { return null; }
}

async function fetchPoolFeeAPR(pos) {
  const chainId  = state.chainId;
  const network  = GT_NETWORK[chainId];
  if (!network) return null;
  // Use the on-chain verified pool address stored during fetchPositions (no CREATE2 guessing)
  const poolAddr = pos.poolAddress;
  if (!poolAddr) return null;
  const cacheKey = poolAddr.toLowerCase();
  if (_aprCache[cacheKey] !== undefined) return _aprCache[cacheKey];
  try {
    const res = await fetch(
      `https://api.geckoterminal.com/api/v2/networks/${network}/pools/${cacheKey}`,
      { headers: { 'Accept': 'application/json' } }
    );
    if (!res.ok) { _aprCache[cacheKey] = null; return null; }
    const data  = await res.json();
    const attrs = data?.data?.attributes;
    const vol24h = parseFloat(attrs?.volume_usd?.h24 || 0);
    const tvl    = parseFloat(attrs?.reserve_in_usd  || 0);
    if (!vol24h || !tvl || tvl < 1) { _aprCache[cacheKey] = null; return null; }
    const feeFrac = pos.fee / 1_000_000;   // 500 → 0.0005
    const apr     = (vol24h * feeFrac / tvl) * 365;  // annualised fraction
    _aprCache[cacheKey] = { apr };
    return { apr };
  } catch { _aprCache[cacheKey] = null; return null; }
}

async function loadPositionAPR(pos) {
  const tokenId     = pos.tokenId;
  const aprEl       = document.getElementById(`pc-apr-${tokenId}`);
  const projEl      = document.getElementById(`pc-proj-${tokenId}`);
  if (!aprEl && !projEl) return;

  const data = await fetchPoolFeeAPR(pos);
  if (!data) {
    // Clear "cargando…" gracefully
    const projElFallback = document.getElementById(`pc-proj-${tokenId}`);
    if (projElFallback) projElFallback.innerHTML = `<div class="pc-proj-label-row" style="color:var(--color-text-muted)">Fee APR — datos no disponibles</div>`;
    return;
  }

  const { apr } = data;
  const aprPct = (apr * 100).toFixed(1);

  if (aprEl) {
    aprEl.textContent = `${aprPct}% Fee APR`;
    aprEl.style.color = apr > 0.5 ? '#34d399' : apr > 0.1 ? '#fbbf24' : '#9ca3af';
  }

  const { amount0, amount1 } = computePositionAmounts(
    pos.sqrtPriceX96, pos.tickLower, pos.tickUpper, pos.liquidity,
    pos.token0Info.decimals, pos.token1Info.decimals
  );
  const usd0 = tokenToUsd(pos.token0Info.symbol, amount0);
  const usd1 = tokenToUsd(pos.token1Info.symbol, amount1);
  const poolVal = (usd0 !== null && usd1 !== null) ? usd0 + usd1 : 0;
  if (!poolVal || !projEl) return;

  const daily   = poolVal * apr / 365;
  const weekly  = daily * 7;
  const monthly = daily * 30;
  const annual  = poolVal * apr;
  projEl.innerHTML = `
    <div class="pc-proj-label-row">Fee Yield Estimado (24h rate × posición)</div>
    <div class="pc-proj-row">
      <span class="pc-proj-item"><span class="pc-proj-period">Diario</span><span class="pc-proj-val">$${daily.toFixed(2)}</span></span>
      <span class="pc-proj-item"><span class="pc-proj-period">Semanal</span><span class="pc-proj-val">$${weekly.toFixed(2)}</span></span>
      <span class="pc-proj-item"><span class="pc-proj-period">Mensual</span><span class="pc-proj-val">$${monthly.toFixed(2)}</span></span>
      <span class="pc-proj-item"><span class="pc-proj-period">Anual</span><span class="pc-proj-val pc-proj-val--annual">$${annual.toFixed(0)}</span></span>
    </div>`;
}

// ── Position Event History ────────────────────────────────────────────────

async function loadPositionEvents(tokenId) {
  const bot = saas.bots[String(tokenId)];
  const el  = document.getElementById(`pos-events-${tokenId}`);
  if (!el || !bot || !saas.jwt) return;

  try {
    const events = await apiCall('GET', `/bots/${bot.id}/events?limit=50`);
    if (!Array.isArray(events) || !events.length) {
      el.innerHTML = `
        <div class="pos-events-header"><span>Eventos del Bot</span></div>
        <div class="pos-events-empty">Sin eventos registrados aún</div>`;
      el.style.display = '';
      return;
    }

    const typeMap = {
      hedge_opened:          { icon: '🔴', label: 'SHORT Abierto',      cls: 'evt-short'   },
      stopped:               { icon: '🟢', label: 'SHORT Cerrado',      cls: 'evt-close'   },
      hedge_closed:          { icon: '🟢', label: 'SHORT Cerrado',      cls: 'evt-close'   },
      breakeven:             { icon: '🟡', label: 'Breakeven',          cls: 'evt-neutral' },
      started:               { icon: '⚙️',  label: 'Bot Iniciado',      cls: 'evt-info'    },
      lp_removed:            { icon: '📤', label: 'LP Removida',        cls: 'evt-info'    },
      lp_burned:             { icon: '🔥', label: 'LP Quemada',         cls: 'evt-info'    },
      bounds_refreshed:      { icon: '🔄', label: 'Rango Actualizado',  cls: 'evt-info'    },
      reentry_guard_cleared: { icon: '🔓', label: 'Re-entrada Lista',   cls: 'evt-info'    },
      error:                 { icon: '⚠️',  label: 'Error',             cls: 'evt-error'   },
    };

    const buildEventRow = (ev, dimmed) => {
      const m     = typeMap[ev.event_type] || { icon: '●', label: ev.event_type.replace(/_/g,' '), cls: 'evt-info' };
      const ts    = ev.ts.endsWith('Z') ? ev.ts : ev.ts + 'Z';
      const time  = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const price = ev.price_at_event
        ? `<span class="evt-price">@ $${Number(ev.price_at_event).toLocaleString('en-US', { maximumFractionDigits: 2 })}</span>`
        : '<span class="evt-price" style="opacity:0"></span>';
      const pnl   = ev.pnl != null
        ? `<span class="evt-pnl ${ev.pnl >= 0 ? 'evt-pnl-pos' : 'evt-pnl-neg'}">${ev.pnl >= 0 ? '+' : ''}$${Number(ev.pnl).toFixed(2)}</span>`
        : '';
      return `<div class="pos-event-row${dimmed ? ' evt-dimmed' : ''}">
        <span class="evt-icon">${m.icon}</span>
        <span class="evt-label ${m.cls}">${m.label}</span>
        ${price}${pnl}
        <span class="evt-time">${time}</span>
      </div>`;
    };

    // Split events into sessions — each "started" event begins a new session.
    // Events arrive newest-first; we reverse to process chronologically then re-reverse.
    const chronological = [...events].reverse();
    const sessions = [];
    let current = null;
    for (const ev of chronological) {
      if (ev.event_type === 'started' || current === null) {
        current = { startedAt: ev.ts, events: [] };
        sessions.push(current);
      }
      current.events.push(ev);
    }
    sessions.reverse(); // latest session first

    let html = '';
    sessions.forEach((sess, idx) => {
      const isLatest  = idx === 0;
      const sessId    = `evt-sess-${tokenId}-${idx}`;
      const ts        = sess.startedAt.endsWith('Z') ? sess.startedAt : sess.startedAt + 'Z';
      const dateLabel = new Date(ts).toLocaleDateString('es', { day: '2-digit', month: 'short' });
      const timeLabel = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const count     = sess.events.length;
      const evRows    = sess.events.map(ev => buildEventRow(ev, !isLatest)).join('');

      if (isLatest) {
        html += `<div class="pos-events-list">${evRows}</div>`;
      } else {
        html += `
          <div class="evt-session-header" onclick="toggleEvtSession('${sessId}')">
            <span class="evt-session-chevron" id="${sessId}-chev">▶</span>
            <span class="evt-session-label">Sesión anterior &middot; ${dateLabel} ${timeLabel}</span>
            <span class="evt-session-count">${count} evento${count !== 1 ? 's' : ''}</span>
          </div>
          <div class="evt-session-body hidden" id="${sessId}">${evRows}</div>`;
      }
    });

    el.innerHTML = `
      <div class="pos-events-header">
        <span>Eventos del Bot</span>
        <span class="pos-events-count">${sessions[0]?.events.length ?? 0} en sesión</span>
      </div>
      ${html}`;
    el.style.display = '';
  } catch (e) {
    // Silently skip — non-critical
  }
}

window.toggleEvtSession = function (sessId) {
  const body  = document.getElementById(sessId);
  const chev  = document.getElementById(`${sessId}-chev`);
  if (!body) return;
  const opening = body.classList.contains('hidden');
  body.classList.toggle('hidden', !opening);
  if (chev) chev.textContent = opening ? '▼' : '▶';
};

function buildPositionCard(pos) {
  const { tokenId, token0Info, token1Info, fee, priceLower, priceUpper, priceCurrent,
          priceBase, rangeStatus, rangePercent, liquidity, tokensOwed0, tokensOwed1,
          tickLower, tickUpper, sqrtPriceX96 } = pos;

  const card = document.createElement('div');
  card.className = 'pos-card ' + (rangeStatus === 'in-range' ? 'in-range'
                                  : rangeStatus === 'out-low'  ? 'out-low'
                                  : rangeStatus === 'out-high' ? 'out-high'
                                  : liquidity === 0n           ? 'zero-liq'
                                  : '');

  // Status badge props
  const statusClass = rangeStatus === 'in-range' ? 'in-range'
                    : rangeStatus === 'out-low'   ? 'out-low'
                    : rangeStatus === 'out-high'  ? 'out-high'
                    : 'zero-liq';
  const t = window.t || (k => k);
  const statusLabel = rangeStatus === 'in-range' ? t('pos.status.inrange')
                    : rangeStatus === 'out-low'   ? t('pos.status.outlow')
                    : rangeStatus === 'out-high'  ? t('pos.status.outhigh')
                    : rangeStatus === 'closed'    ? t('pos.status.closed')
                    : '–';
  const dotClass = rangeStatus === 'in-range' ? 'dot-green'
                 : rangeStatus === 'out-low'   ? 'dot-red'
                 : rangeStatus === 'out-high'  ? 'dot-yellow'
                 : 'dot-gray';

  const feeDisplay = (fee / 10000).toFixed(fee === 100 ? 3 : fee === 500 ? 2 : 1) + '%';
  const pairLabel  = `${token0Info.symbol} / ${token1Info.symbol}`;

  // Range bar cursor position
  const cursorLeft = rangePercent !== null
    ? Math.max(4, Math.min(96, rangePercent))
    : 50;
  const cursorClass = rangeStatus === 'out-low'  ? 'cursor-low'
                    : rangeStatus === 'out-high' ? 'cursor-high'
                    : '';

  // Range % text
  let rangePctText = '';
  if (rangePercent !== null && rangeStatus === 'in-range') {
    rangePctText = `<strong>${rangePercent.toFixed(1)}%</strong> ${t('pos.range.through')}`;
  } else if (rangeStatus === 'out-low') {
    rangePctText = t('pos.range.outlow');
  } else if (rangeStatus === 'out-high') {
    rangePctText = t('pos.range.outhigh');
  } else if (rangeStatus === 'closed') {
    rangePctText = t('pos.range.closed');
  }

  // Fees owed display
  const fee0Display = formatTokenAmount(tokensOwed0, token0Info.decimals);
  const fee1Display = formatTokenAmount(tokensOwed1, token1Info.decimals);
  const hasFees     = tokensOwed0 > 0n || tokensOwed1 > 0n;

  // Pool value in USD
  const { amount0, amount1 } = computePositionAmounts(
    sqrtPriceX96, tickLower, tickUpper, liquidity,
    token0Info.decimals, token1Info.decimals
  );
  const usd0 = tokenToUsd(token0Info.symbol, amount0);
  const usd1 = tokenToUsd(token1Info.symbol, amount1);
  const poolValueUsd = (usd0 !== null && usd1 !== null) ? usd0 + usd1 : null;

  // Uncollected fees USD value
  const fees0Human = Number(tokensOwed0) / Math.pow(10, token0Info.decimals);
  const fees1Human = Number(tokensOwed1) / Math.pow(10, token1Info.decimals);
  const feeUsd0 = tokenToUsd(token0Info.symbol, fees0Human);
  const feeUsd1 = tokenToUsd(token1Info.symbol, fees1Human);
  const feesValueUsd = (feeUsd0 !== null && feeUsd1 !== null) ? feeUsd0 + feeUsd1 : null;

  card.innerHTML = `
    <div class="pc-header">
      <div>
        <div class="pc-id">NFT #${tokenId}</div>
        <div class="pc-pair">${pairLabel}</div>
        <div class="pc-fee">${t('pos.fee.tier')} ${feeDisplay}</div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
        <div class="pc-status ${statusClass}">
          <span class="status-dot ${dotClass}"></span>
          ${statusLabel}
        </div>
        <div class="pc-apr-badge" id="pc-apr-${tokenId}">APR —</div>
      </div>
    </div>

    <div class="pc-divider"></div>

    <div class="pc-range-section">
      <div class="pc-range-label">${t('pos.range.label')} (${priceBase})</div>
      <div class="range-bar-wrap">
        <div class="range-bar-track">
          <div class="range-bar-fill"></div>
          ${priceCurrent !== null
            ? `<div class="range-bar-cursor ${cursorClass}" style="left:${cursorLeft}%"></div>`
            : ''}
        </div>
        <div class="range-bar-labels">
          <span class="rbl-lower">${formatPrice(priceLower)}</span>
          <span class="rbl-upper">${formatPrice(priceUpper)}</span>
        </div>
      </div>
    </div>

    <div class="pc-prices">
      <div class="pc-price-item">
        <div class="pc-price-label">${t('pos.price.lower')}</div>
        <div class="pc-price-value lower">${formatPrice(priceLower)}</div>
      </div>
      <div class="pc-price-item">
        <div class="pc-price-label">${t('pos.price.current')}</div>
        <div class="pc-price-value current">${priceCurrent !== null ? formatPrice(priceCurrent) : '—'}</div>
      </div>
      <div class="pc-price-item">
        <div class="pc-price-label">${t('pos.price.upper')}</div>
        <div class="pc-price-value upper">${formatPrice(priceUpper)}</div>
      </div>
    </div>

    ${rangePctText
      ? `<div class="pc-range-pct">${rangePctText}</div>`
      : ''}

    ${poolValueUsd !== null ? `
    <div class="pc-pool-value">
      <div class="pc-fees-label">Pool Value</div>
      <div class="pc-fees-values" style="font-size:1.05rem;font-weight:700;color:#e2e8f0">
        $${poolValueUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        <span style="font-size:0.72rem;font-weight:400;color:var(--color-text-secondary);margin-left:6px">
          ${amount0.toFixed(4)} ${token0Info.symbol} + ${amount1.toFixed(2)} ${token1Info.symbol}
        </span>
      </div>
    </div>` : ''}

    <div class="pc-proj-section" id="pc-proj-${tokenId}">
      <div class="pc-proj-label-row">Fee Yield Estimado — cargando…</div>
    </div>

    <div class="pc-fees">
      <div class="pc-fees-label">${t('pos.fees.label')}${feesValueUsd !== null && feesValueUsd > 0 ? ` <span style="color:#34d399;font-size:0.72rem">≈ $${feesValueUsd.toFixed(2)}</span>` : ''}</div>
      <div class="pc-fees-values">
        ${hasFees
          ? `${fee0Display}<span>${token0Info.symbol}</span>&nbsp;+&nbsp;${fee1Display}<span>${token1Info.symbol}</span>`
          : '<span style="color:var(--color-text-muted)">—</span>'}
      </div>
    </div>

    ${buildProtectionDrawer(pos)}
    <div id="pos-events-${tokenId}" class="pos-events-section" style="display:none"></div>
  `;

  return card;
}

// ── Uniswap v3 Pool Value Math ────────────────────────────────────────────

/**
 * Compute token0 and token1 amounts from a v3 position.
 * Returns { amount0, amount1 } as human-readable floats (post-decimal).
 */
function computePositionAmounts(sqrtPriceX96, tickLower, tickUpper, liquidity, decimals0, decimals1) {
  if (!sqrtPriceX96 || liquidity === 0n) return { amount0: 0, amount1: 0 };

  const Q96 = 2 ** 96;
  const sqrtP  = Number(sqrtPriceX96) / Q96;
  const sqrtA  = Math.sqrt(Math.pow(1.0001, tickLower));
  const sqrtB  = Math.sqrt(Math.pow(1.0001, tickUpper));
  const liq    = Number(liquidity);

  let raw0 = 0, raw1 = 0;
  if (sqrtP <= sqrtA) {
    // All token0
    raw0 = liq * (sqrtB - sqrtA) / (sqrtA * sqrtB);
  } else if (sqrtP >= sqrtB) {
    // All token1
    raw1 = liq * (sqrtB - sqrtA);
  } else {
    raw0 = liq * (sqrtB - sqrtP) / (sqrtP * sqrtB);
    raw1 = liq * (sqrtP - sqrtA);
  }

  return {
    amount0: raw0 / Math.pow(10, decimals0),
    amount1: raw1 / Math.pow(10, decimals1),
  };
}

/**
 * Convert token symbol + amount to USD using live prices.
 * Returns null if price unavailable.
 */
function tokenToUsd(symbol, amount) {
  if (STABLES.has(symbol))       return amount;
  if (symbol === 'WETH')         return state.prices.eth  ? amount * state.prices.eth  : null;
  if (symbol === 'WBTC')         return state.prices.btc  ? amount * state.prices.btc  : null;
  return null;
}

// ── UI Helpers ────────────────────────────────────────────────────────────

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

function setWalletBtnLoading(loading) {
  const btn = document.getElementById('wallet-btn');
  btn.disabled  = loading;
  btn.textContent = loading
    ? (window.t ? window.t('dash.btn.connecting') : '⏳ Connecting…')
    : (window.t ? window.t('dash.btn.connect')    : '🟢 Connect Wallet');
}

function showError(msg) {
  console.error(msg);
  const el = document.getElementById('error-banner');
  if (!el) return;
  el.textContent = '⚠ ' + msg;
  el.classList.remove('hidden');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add('hidden'), 8000);
}

function showSessionExpiredBanner() {
  const t  = window.t || (k => k);
  const el = document.getElementById('session-expired-banner');
  if (!el) return;
  el.classList.remove('hidden');
}

function hideSessionExpiredBanner() {
  const el = document.getElementById('session-expired-banner');
  if (el) el.classList.add('hidden');
}

// ── Init ──────────────────────────────────────────────────────────────────

function init() {
  // Start in disconnected state
  renderConnectPrompt();

  // Detect wallet type for UX messaging
  if (!window.ethereum) {
    document.getElementById('no-wallet-msg').style.display = 'block';
  } else if (window.ethereum.isRabby) {
    // Rabby detected — tweak copy
    const hint = document.querySelector('.connect-hint');
    if (hint) hint.textContent = window.t ? window.t('dash.rabby.detected') : 'Rabby Wallet detected ✓';
  }

  // Close wallet dropdown when clicking outside it
  document.addEventListener('click', e => {
    const wrapper = document.getElementById('wallet-dropdown-wrapper');
    if (wrapper && !wrapper.contains(e.target)) closeWalletDropdown();
  });

  // Enter key on watch address input
  const watchInput = document.getElementById('watch-addr-input');
  if (watchInput) {
    watchInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') startWatchMode();
    });
  }

  // Start price ticker even before wallet connects
  fetchLivePrices();

  // Check if wallet already authorized (no popup)
  if (window.ethereum) {
    window.ethereum.request({ method: 'eth_accounts' }).then(accounts => {
      if (accounts.length) {
        state.provider = new ethers.BrowserProvider(window.ethereum);
        state.address  = accounts[0];
        state.provider.getNetwork().then(net => {
          state.chainId = Number(net.chainId);
          onWalletConnected();
        }).catch(() => {});
      }
    }).catch(() => {});
  }
}

// Wait for ethers.js CDN to load
if (typeof ethers !== 'undefined') {
  init();
} else {
  window.addEventListener('load', init);
}

// ═══════════════════════════════════════════════════════════════════════════
// SaaS — Auth, Bot Management, Protection Drawer (Phase 4)
// ═══════════════════════════════════════════════════════════════════════════

// ── API helper ────────────────────────────────────────────────────────────

async function apiCall(method, path, body) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(saas.jwt ? { Authorization: `Bearer ${saas.jwt}` } : {}),
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  if (res.status === 401) {
    saas.sessionExpired = true;
    saas.jwt = null;
    localStorage.removeItem('vf_jwt');
    showSessionExpiredBanner();
    renderPositions();
    throw new Error('Session expired — please sign in again.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────

window.saasSignIn = async function () {
  if (!state.provider || !state.address || state.watchMode) return;
  try {
    const signerBtn = document.getElementById('prot-signin-spinner');
    if (signerBtn) signerBtn.textContent = '⏳';

    // 1. Get nonce from API
    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${state.address}`);
    if (!nonceRes.ok) throw new Error('Could not get nonce from server');
    const { nonce } = await nonceRes.json();

    // 2. Sign with wallet
    const signer  = await state.provider.getSigner();
    const message = `Sign in to VIZNIAGO FURY\nNonce: ${nonce}`;
    const signature = await signer.signMessage(message);

    // 3. Verify and get JWT
    const verRes = await fetch(`${API_BASE}/auth/verify`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ address: state.address, signature }),
    });
    if (!verRes.ok) throw new Error('Signature verification failed');
    const { access_token } = await verRes.json();

    saas.jwt = access_token;
    saas.sessionExpired = false;
    localStorage.setItem('vf_jwt', access_token);
    hideSessionExpiredBanner();
    updateNuclearBtn();

    await saasLoadBots();
    renderPositions(); // re-render so drawers show forms
  } catch (err) {
    if (err.code === 4001) return; // user rejected wallet popup
    showError('Sign-in failed: ' + (err.message || err));
  }
};

// ── Admin helpers ─────────────────────────────────────────────────────────

function jwtIsAdmin(token) {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.is_admin === true;
  } catch { return false; }
}

function updateNuclearBtn() {
  const btn = document.getElementById('nuclear-stop-btn');
  if (!btn) return;
  if (jwtIsAdmin(saas.jwt)) {
    btn.classList.remove('hidden');
  } else {
    btn.classList.add('hidden');
  }
}

window.nuclearStop = function () {
  document.getElementById('nuclear-result').textContent = '';
  document.getElementById('nuclear-modal').classList.remove('hidden');
};

window.closeNuclearModal = function (e) {
  if (e && e.target !== document.getElementById('nuclear-modal')) return;
  document.getElementById('nuclear-modal').classList.add('hidden');
};

window.confirmNuclearStop = async function () {
  const confirmBtn = document.querySelector('.btn-nuclear-confirm');
  const result     = document.getElementById('nuclear-result');
  confirmBtn.disabled = true;
  confirmBtn.textContent = '⏳ Deteniendo…';
  try {
    const data = await apiCall('POST', '/admin/stop-all');
    result.style.color = '#00ffb3';
    result.textContent = `✓ ${data.stopped_count} bot(s) detenidos.`;
    confirmBtn.textContent = '✓ Hecho';
    await saasLoadBots();
    renderPositions();
  } catch (err) {
    result.style.color = '#f87171';
    result.textContent = `Error: ${err.message}`;
    confirmBtn.disabled = false;
    confirmBtn.textContent = '☢ Confirmar Parada Total';
  }
};

// ── Bot loading ───────────────────────────────────────────────────────────

async function saasLoadBots() {
  if (!saas.jwt) return;
  try {
    const bots = await apiCall('GET', '/bots');
    if (!Array.isArray(bots)) return;
    saas.bots = {};
    for (const bot of bots) {
      saas.bots[bot.nft_token_id] = bot;
    }
    // Pre-populate last event status from API, then open WebSocket
    for (const bot of bots) {
      if (bot.active) {
        // Fetch last known event so panel shows real data immediately after refresh
        apiCall('GET', `/bots/${bot.id}/status`).then(s => {
          if (s?.last_event) saas.statuses[bot.id] = s.last_event;
          renderLiveBots();
        }).catch(() => {});
        // 1. Pre-populate from localStorage cache (raw lines, 72h TTL)
        const cached = loadLogCache(bot.id);
        if (cached.length) {
          saas.logs[bot.id] = cached.map(e => e.msg);
          renderLiveBots();
        }
        // 2. Append structured DB events (last 72h) on top of cache
        apiCall('GET', `/bots/${bot.id}/events?limit=200&hours=72`).then(events => {
          if (!Array.isArray(events) || !events.length) return;
          if (!saas.logs[bot.id]) saas.logs[bot.id] = [];
          const now = Date.now();
          // Events come newest-first — reverse to show oldest at top
          [...events].reverse().forEach(ev => {
            const d    = new Date(ev.ts);
            const ageH = (now - d.getTime()) / 3_600_000;
            const ts   = ageH > 6
              ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString()
              : d.toLocaleTimeString();
            const pnl = ev.pnl != null ? ` | P&L: ${ev.pnl >= 0 ? '+' : ''}$${Number(ev.pnl).toFixed(2)}` : '';
            const px  = ev.price_at_event ? ` | $${Number(ev.price_at_event).toLocaleString('en-US',{maximumFractionDigits:2})}` : '';
            saas.logs[bot.id].push(`[${ts}] ${ev.event_type.toUpperCase()}${px}${pnl}`);
          });
          renderLiveBots();
        }).catch(() => {});
        if (!saas.sockets[bot.id]) connectBotWS(bot.id);
      }
    }
    // Re-render positions and live bots panel
    if (state.positions.length > 0) renderPositions();
    renderLiveBots();
    // Check Telegram link status (fire-and-forget, updates wallet dropdown)
    loadTgLinkStatus();
  } catch (err) {
    // Silently ignore — JWT may be expired (apiCall handles 401)
    console.warn('[SaaS] loadBots:', err.message);
  }
}

// ── Live Bots Panel ───────────────────────────────────────────────────────

function renderLiveBots() {
  const section = document.getElementById('live-bots-section');
  if (!section) return;
  const t = window.t || (k => k);

  const activeBots = Object.values(saas.bots).filter(b => b.active);

  if (!activeBots.length) {
    section.innerHTML = '';
    return;
  }

  const cards = activeBots.map(bot => {
    const lastEvt = saas.statuses[bot.id];
    const lastEvtHtml = lastEvt
      ? `<div class="hi-label" style="margin-top:10px">${t('prot.lastevent')}</div>
         <div class="hi-value" style="font-size:0.7rem" id="live-bot-evt-${bot.id}">
           ${(lastEvt.event||'').replace(/_/g,' ')} · ${lastEvt.price ? formatPrice(lastEvt.price) : '—'}
         </div>`
      : `<div class="hi-value" style="font-size:0.7rem" id="live-bot-evt-${bot.id}">${t('prot.status.checking')}</div>`;

    if (bot.mode === 'fury') {
      const symbol     = (bot.fury_symbol || 'ETH').toUpperCase();
      const isPaper    = bot.paper_trade === true;
      const statusTag  = isPaper
        ? `<span class="status-live-tag" style="background:#f59e0b;color:#000">PAPER</span>`
        : `<span class="status-dot dot-green"></span><span class="status-live-tag">LIVE</span>`;
      return `
        <div class="hedge-panel" style="margin-top:16px">
          <div class="hedge-panel-header">
            <div class="section-label">VIZNIAGO FURY</div>
            <h3 class="hedge-panel-title">
              RSI Trader · ${symbol} ${statusTag}
            </h3>
          </div>
          <div class="hedge-info-grid">
            <div class="hedge-info-card">
              <div class="hi-label">Symbol</div>
              <div class="hi-value text-neon">${symbol}/USDC</div>
              <div class="hi-sub">Hyperliquid Perps</div>
            </div>
            <div class="hedge-info-card">
              <div class="hi-label">RSI Period / Thresholds</div>
              <div class="hi-value">${bot.fury_rsi_period || 9}</div>
              <div class="hi-sub">Long ≤ ${bot.fury_rsi_long_th || 35} · Short ≥ ${bot.fury_rsi_short_th || 65}</div>
            </div>
            <div class="hedge-info-card">
              <div class="hi-label">Max Leverage</div>
              <div class="hi-value text-neon">${bot.fury_leverage_max || 12}×</div>
              <div class="hi-sub">Risk ${bot.fury_risk_pct || 2}% / trade</div>
            </div>
            <div class="hedge-info-card">
              <div class="hi-label">Mode</div>
              <div class="hi-value" style="font-size:0.75rem">${isPaper ? '📋 Paper Trade' : '🔴 Live'}</div>
              ${lastEvtHtml}
            </div>
          </div>
          ${buildLogTerminal(bot.id)}
        </div>`;
    }

    // Whale bots are managed via the dedicated Whale Tracker page (/whale/)
    if (bot.mode === 'whale') return '';
    // ─────────────────────────────────────────────────────────────────────

    const modeName      = bot.mode === 'aragan'
      ? t('dash.hedge.mode.val')
      : 'Defensor Alcista (Cobertura + Long)';
    const lowerTrigPx   = bot.lower_bound * (1 + bot.trigger_pct / 100);
    const upperTrigPx   = bot.upper_bound * (1 - bot.trigger_pct / 100);
    const rangePct      = (((bot.upper_bound - bot.lower_bound) / bot.lower_bound) * 100).toFixed(1);
    const chainName     = { 42161: 'Arbitrum', 1: 'Ethereum', 8453: 'Base' }[bot.chain_id] || `Chain ${bot.chain_id}`;

    // Distance to nearest trigger using live position price
    const matchPos      = state.positions.find(p => String(p.tokenId) === String(bot.nft_token_id));
    const curPrice      = matchPos?.priceCurrent ?? null;
    let distanceHtml    = '';
    if (curPrice !== null) {
      const distLower   = ((curPrice - lowerTrigPx) / curPrice) * 100;
      const distUpper   = ((upperTrigPx - curPrice) / curPrice) * 100;
      const nearest     = Math.abs(distLower) <= Math.abs(distUpper) ? distLower : distUpper;
      const nearestDir  = Math.abs(distLower) <= Math.abs(distUpper) ? '↓' : '↑';
      const distColor   = Math.abs(nearest) < 2 ? '#f87171' : Math.abs(nearest) < 5 ? '#fbbf24' : '#34d399';
      distanceHtml = `
        <div class="hedge-distance-row">
          <span class="hedge-dist-label">DISTANCIA</span>
          <span class="hedge-dist-value" style="color:${distColor}">${nearestDir} ${Math.abs(nearest).toFixed(2)}% al trigger</span>
          <span class="hedge-dist-price">precio actual $${Number(curPrice).toLocaleString('en-US',{maximumFractionDigits:2})}</span>
        </div>`;
    }

    return `
      <div class="hedge-panel" style="margin-top:16px">
        <div class="hedge-panel-header">
          <div class="section-label">${t('dash.hedge.label')}</div>
          <h3 class="hedge-panel-title">
            ${bot.mode === 'aragan' ? 'Defensor Bajista' : 'Defensor Alcista'} v1.3
            <span class="status-dot dot-green"></span>
            <span class="status-live-tag">LIVE</span>
          </h3>
        </div>
        <div class="hedge-info-grid">
          <div class="hedge-info-card">
            <div class="hi-label">${t('dash.hedge.nft.label')}</div>
            <div class="hi-value text-neon">#${bot.nft_token_id}</div>
            <div class="hi-sub">${bot.pair} · ${chainName}</div>
          </div>
          <div class="hedge-info-card">
            <div class="hi-label">${t('dash.hedge.range.label')}</div>
            <div class="hi-value">$${Number(bot.lower_bound).toLocaleString('en-US',{maximumFractionDigits:2})} — $${Number(bot.upper_bound).toLocaleString('en-US',{maximumFractionDigits:2})}</div>
            <div class="hi-sub">~${rangePct}% ${t('dash.hedge.range.width')}</div>
          </div>
          <div class="hedge-info-card">
            <div class="hi-label">↓ Trigger Bajista</div>
            <div class="hi-value text-neon">$${Number(lowerTrigPx).toLocaleString('en-US',{maximumFractionDigits:2})}</div>
            <div class="hi-sub">${Math.abs(bot.trigger_pct)}% bajo el piso</div>
          </div>
          <div class="hedge-info-card">
            <div class="hi-label">↑ Trigger Alcista</div>
            <div class="hi-value" style="color:#fbbf24">$${Number(upperTrigPx).toLocaleString('en-US',{maximumFractionDigits:2})}</div>
            <div class="hi-sub">${Math.abs(bot.trigger_pct)}% sobre el techo</div>
          </div>
        </div>
        ${distanceHtml}
        <div class="hedge-rule">
          <span class="hedge-rule-icon">&#9888;</span>
          <span data-i18n-html="dash.hedge.rule">${t('dash.hedge.rule')}</span>
        </div>
        ${buildLogTerminal(bot.id)}
      </div>`;
  }).join('');

  section.innerHTML = cards;
}

// ── Log terminal ──────────────────────────────────────────────────────────

function appendLogLine(configId, msg) {
  const el = document.getElementById(`bot-log-${configId}`);
  if (!el) return;
  const line = document.createElement('div');
  line.className = 'bot-log-line';
  // Colour-code key words
  const escaped = msg
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  line.innerHTML = escaped
    .replace(/(TRIGGERED|HEDGE|SHORT|LONG|TP|SL|ERROR)/g, '<span class="log-warn">$1</span>')
    .replace(/(IN RANGE|✅|🟢)/g, '<span class="log-ok">$1</span>')
    .replace(/(OUT|⚠|🔴|❌)/g,   '<span class="log-alert">$1</span>');
  el.appendChild(line);
  // Keep only last LOG_MAX lines in DOM
  while (el.children.length > LOG_MAX) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

function buildLogTerminal(configId) {
  const lines = (saas.logs[configId] || []).map(msg => {
    const escaped = msg
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<div class="bot-log-line">${escaped
      .replace(/(TRIGGERED|HEDGE|SHORT|LONG|TP|SL|ERROR)/g, '<span class="log-warn">$1</span>')
      .replace(/(IN RANGE|✅|🟢)/g, '<span class="log-ok">$1</span>')
      .replace(/(OUT|⚠|🔴|❌)/g,   '<span class="log-alert">$1</span>')
    }</div>`;
  }).join('');
  return `
    <div class="bot-log-header">
      <span class="bot-log-title">&#9654; LIVE LOG</span>
      <span class="bot-log-dot"></span>
      <button class="bot-log-clear" onclick="clearBotLog(${configId})" title="Clear log">&#10005;</button>
    </div>
    <div class="bot-log-terminal" id="bot-log-${configId}">${lines}</div>`;
}

function clearBotLog(configId) {
  saas.logs[configId] = [];
  clearLogCache(configId);
  const el = document.getElementById(`bot-log-${configId}`);
  if (el) el.innerHTML = '';
}

// ── WebSocket per bot ─────────────────────────────────────────────────────

function connectBotWS(configId) {
  if (saas.sockets[configId]) return; // already connected
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}/trading/lp-hedge/api/ws/${configId}?token=${saas.jwt}`;
  const ws    = new WebSocket(url);
  saas.sockets[configId] = ws;

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.event === 'ping') return;

      if (data.type === 'log') {
        // Raw stdout line — append to log buffer, persist to cache, update terminal
        if (!saas.logs[configId]) saas.logs[configId] = [];
        saas.logs[configId].push(data.msg);
        if (saas.logs[configId].length > LOG_MAX) saas.logs[configId].shift();
        pushLogCache(configId, data.msg);
        appendLogLine(configId, data.msg);
      } else {
        // Structured event
        saas.statuses[configId] = data;
        updateBotStatusDisplay(configId, data);
        updateWalletDropdown();
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    delete saas.sockets[configId];
    // Reconnect after 10 s if the bot is still marked active
    setTimeout(() => {
      const bot = Object.values(saas.bots).find(b => b.id === configId);
      if (bot?.active && saas.jwt) connectBotWS(configId);
    }, 10_000);
  };

  ws.onerror = () => ws.close();
}

function updateBotStatusDisplay(configId, data) {
  const t       = window.t || (k => k);
  const evtType = (data.event || data.event_type || '').replace(/_/g, ' ');
  const price   = data.price ? formatPrice(data.price) : '—';
  const pnl     = data.pnl != null
    ? (data.pnl >= 0 ? '+' : '') + '$' + Number(data.pnl).toFixed(2) : '—';
  const html = `<span class="prot-evt-type">${evtType}</span>`
    + ` &middot; ${t('prot.price')}: ${price}`
    + ` &middot; P&L: ${pnl}`;

  // Update protection drawer status row
  const drawerEl = document.getElementById(`prot-status-${configId}`);
  if (drawerEl) drawerEl.innerHTML = html;

  // Update live bots panel
  const panelEl = document.getElementById(`live-bot-evt-${configId}`);
  if (panelEl) panelEl.innerHTML = `${evtType} · ${price}`;
}

// ── Protection Drawer HTML builder ────────────────────────────────────────

function buildProtectionDrawer(pos) {
  const t       = window.t || (k => k);
  const tokenId = pos.tokenId;
  const bot     = saas.bots[tokenId];
  const isOpen  = _drawerOpen.has(tokenId);

  // Badge shown on toggle row
  const badge = bot
    ? `<span class="prot-badge ${bot.active ? 'prot-badge--active' : 'prot-badge--inactive'}">`
        + (bot.active ? t('prot.status.active') : t('prot.status.inactive'))
        + `</span>`
    : '';

  const isBTC = ['BTC', 'WBTC'].some(s =>
    pos.token0Info.symbol.includes(s) || pos.token1Info.symbol.includes(s)
  );

  let bodyHtml;

  if (state.watchMode || pos._exploreOnly) {
    // Watch / explore mode — no protection available
    bodyHtml = `<p class="prot-info-msg">${t('prot.watch.disabled')}</p>`;

  } else if (!saas.jwt && saas.sessionExpired) {
    // Session expired — bot may still be running server-side
    bodyHtml = `
      <div class="prot-session-expired">
        <span class="prot-session-expired-icon">⏰</span>
        <p class="prot-session-expired-msg">${t('prot.session.expired.msg')}</p>
      </div>
      <button class="btn btn-primary btn-sm prot-btn-full" onclick="saasSignIn()">
        🔐&nbsp; ${t('prot.btn.reauth')}
      </button>`;

  } else if (!saas.jwt) {
    // New user — never signed in
    bodyHtml = `
      <p class="prot-info-msg">${t('prot.drawer.signin.hint')}</p>
      <button class="btn btn-primary btn-sm prot-btn-full" onclick="saasSignIn()">
        🔐&nbsp; ${t('prot.btn.signin')}
      </button>`;

  } else if (bot && bot.active) {
    // Bot is active — show live status + stop button
    const lastEvt = saas.statuses[bot.id];
    const statusInner = lastEvt
      ? (() => {
          const evtType = lastEvt.event || lastEvt.event_type || '';
          const price   = lastEvt.price ? formatPrice(lastEvt.price) : '—';
          const pnl     = lastEvt.pnl != null
            ? (lastEvt.pnl >= 0 ? '+' : '') + '$' + Number(lastEvt.pnl).toFixed(2) : '—';
          return `<span class="prot-evt-type">${evtType.replace(/_/g,' ')}</span>`
            + ` &middot; ${t('prot.price')}: ${price} &middot; P&L: ${pnl}`;
        })()
      : t('prot.status.checking');

    const hlBalActive = _hlBalanceCache?.account_value;
    bodyHtml = `
      <div class="prot-hl-balance-bar">
        <span class="prot-hl-bal-label">HL Balance</span>
        <span class="prot-hl-bal-value">${hlBalActive != null ? '$' + Number(hlBalActive).toFixed(2) : '—'}</span>
      </div>
      <div class="prot-status-row" id="prot-status-${bot.id}">${statusInner}</div>
      <div class="prot-active-info">
        <div class="prot-info-item">
          <span class="prot-info-label">${t('prot.mode.label')}</span>
          <span class="prot-info-value">${bot.mode === 'aragan' ? 'Defensor Bajista' : 'Defensor Alcista'}</span>
        </div>
        <div class="prot-info-item">
          <span class="prot-info-label">Leverage</span>
          <span class="prot-info-value">${bot.leverage ?? 10}x</span>
        </div>
        <div class="prot-info-item">
          <span class="prot-info-label">Stop Loss</span>
          <span class="prot-info-value">${bot.sl_pct ?? 0.1}%</span>
        </div>
        <div class="prot-info-item">
          <span class="prot-info-label">${t('prot.trigger.label')}
            <span class="tp-info-anchor" tabindex="0" aria-label="Qué es esto">❓
              <span class="tp-info-popover tp-info-popover--left">
                <strong>¿Cuándo dispara el bot?</strong><br><br>
                Cuando el precio cae este % por debajo del <em>piso</em> de tu rango LP, el bot abre la cobertura SHORT automáticamente.<br><br>
                <span style="color:#00d4ff">Ej: Piso $2,030 · -0.5% → SHORT se abre en $2,020</span><br><br>
                ⚠️ <strong>No es el Stop Loss</strong> — el SL es un campo separado.
              </span>
            </span>
          </span>
          <span class="prot-info-value">${bot.trigger_pct}%</span>
        </div>
        <div class="prot-info-item">
          <span class="prot-info-label">${t('prot.hedgesize.label')}</span>
          <span class="prot-info-value">${bot.hedge_ratio}%</span>
        </div>
        <div class="prot-info-item">
          <span class="prot-info-label">Trailing / Rearm</span>
          <span class="prot-info-value">${bot.trailing_stop ? '✓' : '✗'} / ${bot.auto_rearm ? '✓' : '✗'}</span>
        </div>
      </div>
      <button class="btn btn-outline btn-sm prot-btn-full prot-btn-stop" id="prot-stop-btn-${bot.id}"
              onclick="stopProtection(${bot.id}, '${tokenId}')">
        ⏹&nbsp; ${t('prot.btn.stop')}
      </button>`;

  } else {
    // No active bot (or inactive) — show trading panel form
    const modeVal      = bot?.mode          || 'aragan';
    const trigVal      = Math.abs(bot?.trigger_pct ?? 0.50);
    const hedgeVal     = bot?.hedge_ratio   ?? 50;
    const hlWallet     = bot?.hl_wallet_addr || '';
    const leverageVal  = bot?.leverage      ?? 10;
    const slVal        = bot?.sl_pct        ?? 0.10;
    const tpVal        = bot?.tp_pct        ?? '';
    const trailVal     = bot?.trailing_stop ?? true;
    const rearmVal     = bot?.auto_rearm    ?? true;
    const apiKeyPH     = bot
      ? t('prot.apikey.keepcurrent')
      : t('prot.apikey.placeholder');

    const pair  = `${pos.token0Info.symbol}/${pos.token1Info.symbol}`;
    const range = `${formatPrice(pos.priceLower)} – ${formatPrice(pos.priceUpper)}`;

    bodyHtml = isBTC ? `
      <div class="prot-btc-soon">
        <div class="prot-btc-soon-icon">₿</div>
        <p class="prot-btc-soon-title">${t('prot.btc.soon.title')}</p>
        <p class="prot-btc-soon-msg">${t('prot.btc.soon.msg')}</p>
      </div>` : `
      <div class="prot-form" id="prot-form-${tokenId}">

        <!-- Header: pair + range -->
        <div class="tp-header">
          <div class="tp-pair">${pair}</div>
          <div class="tp-range">Range ${range}</div>
        </div>

        <!-- HL Credentials -->
        <div class="prot-field">
          <label class="prot-label prot-label--warning">${t('prot.wallet.label')}</label>
          <input type="text" class="prot-input prot-input-full"
                 id="prot-wallet-${tokenId}" value="${hlWallet}"
                 placeholder="${t('prot.wallet.placeholder')}" />
        </div>
        <div class="prot-field" style="margin-bottom:4px">
          <label class="prot-label prot-label--danger">${t('prot.apikey.label')}</label>
          <input type="password" class="prot-input prot-input-full"
                 id="prot-apikey-${tokenId}" placeholder="${apiKeyPH}" autocomplete="off" />
        </div>
        ${!hlWallet ? `<p style="font-size:0.6rem;color:var(--color-text-muted);margin:0 0 8px">${t('prot.wallet.hint')}</p>` : ''}

        <!-- HL Balance (M2-4) -->
        <div class="prot-hl-balance-bar" id="prot-hl-bal-${tokenId}">
          <span class="prot-hl-bal-label">HL Balance</span>
          <span class="prot-hl-bal-value" id="prot-hl-bal-val-${tokenId}">cargando…</span>
        </div>

        <!-- Mode toggle -->
        <div class="prot-field" style="margin-bottom:10px">
          <label class="prot-label">${t('prot.mode.label')}</label>
          <div class="prot-mode-toggle">
            <label class="prot-mode-opt prot-mode-opt--disabled">
              <input type="radio" name="prot-mode-${tokenId}" value="aragan" disabled />
              <span class="prot-mode-text">
                <span class="prot-mode-name">${t('prot.mode.aragan')} <span class="prot-mode-soon">${t('prot.mode.soon')}</span></span>
                <span class="prot-mode-desc">${t('prot.mode.aragan.desc')}</span>
              </span>
            </label>
            <label class="prot-mode-opt ${isBTC ? 'prot-mode-opt--disabled' : 'prot-mode-opt--active'}">
              <input type="radio" name="prot-mode-${tokenId}" value="avaro"
                     ${!isBTC ? 'checked' : ''}
                     ${isBTC ? 'disabled' : ''}
                     onchange="onModeChange('${tokenId}', this)" />
              <span class="prot-mode-text">
                <span class="prot-mode-name">${t('prot.mode.avaro')}</span>
                <span class="prot-mode-desc">${t('prot.mode.avaro.desc')}</span>
              </span>
            </label>
          </div>
          <p class="prot-mode-neutral-note">${t('prot.mode.neutral.note')}</p>
        </div>

        <!-- Capital por Operación -->
        <div class="tp-capital-row">
          <span class="tp-capital-label">Capital por Operación</span>
          <span>
            <span class="tp-capital-value" id="tp-capital-${tokenId}">—</span>
            <span class="tp-capital-hint"> = hedge notional</span>
          </span>
        </div>

        <!-- Buffer de Confirmación (trigger offset slider — applies to BOTH triggers) -->
        <div class="tp-slider-row">
          <div class="tp-slider-header">
            <span class="tp-slider-label">Buffer de Confirmación
              <span class="tp-info-anchor" tabindex="0" aria-label="Qué es esto">❓
                <span class="tp-info-popover">
                  <strong>¿Cuándo dispara el bot?</strong><br><br>
                  Este % se aplica a <em>ambos</em> disparadores:<br><br>
                  <strong>↑ Desde arriba:</strong> precio cae este % por debajo del <em>techo</em> del rango → SHORT abierto dentro del rango.<br><br>
                  <strong>↓ Ruptura inferior:</strong> precio cae este % por debajo del <em>piso</em> del rango → SHORT de protección IL.<br><br>
                  <span style="color:#00d4ff">Ej con 0.5% (default): Techo $2,100 → disparo en $2,089.5 &nbsp;|&nbsp; Piso $1,900 → disparo en $1,890.5</span><br><br>
                  ⚠️ <strong>No es el Stop Loss</strong> — el SL es un campo separado.
                </span>
              </span>
            </span>
            <span class="tp-slider-value" id="tp-buf-val-${tokenId}">${trigVal.toFixed(1)}%</span>
          </div>
          <input type="range" class="tp-slider" id="prot-trigger-${tokenId}"
                 min="0" max="5" step="0.1" value="${trigVal}"
                 oninput="onTradingPanelChange('${tokenId}')" />
          <div class="tp-slider-range-labels"><span>0%</span><span>5% max</span></div>
        </div>

        <!-- Hedge Size (slider) -->
        <div class="tp-slider-row">
          <div class="tp-slider-header">
            <span class="tp-slider-label">
              Tamaño de Cobertura
              <span class="tp-info-anchor" tabindex="0" aria-label="Qué es esto">❓
                <span class="tp-info-popover">
                  <strong>% de tu exposición máxima ETH que el bot cubrirá con un short.</strong><br><br>
                  Cuando el precio cae a tu límite inferior, tu LP pasa a ser 100% ETH (IL máximo).
                  El bot abre un short equivalente a este porcentaje de ese ETH para compensar.<br><br>
                  <span style="color:#00d4ff">50%</span> → mitad cubierta, menor costo de margen.<br>
                  <span style="color:#00d4ff">100%</span> → cobertura total, delta neutral.<br>
                  <span style="color:#f59e0b">&gt;100%</span> → <strong>Modo Ofensivo</strong>: short mayor que la LP. Ganas más que lo que pierde la LP en bajadas — apuesta direccional.
                </span>
              </span>
            </span>
            <span class="tp-slider-value" id="tp-hedge-val-${tokenId}">${hedgeVal}%</span>
          </div>
          <input type="range" class="tp-slider" id="prot-hedge-${tokenId}"
                 min="10" max="200" step="5" value="${hedgeVal}"
                 oninput="onTradingPanelChange('${tokenId}')" />
          <div class="tp-slider-range-labels"><span>10%</span><span>100% neutral</span><span>200% ofensivo</span></div>
          <div id="tp-offensive-warn-${tokenId}" class="tp-offensive-warn hidden"></div>
          <div class="tp-hedge-sublabel" id="tp-hedge-sub-${tokenId}">calculando…</div>
        </div>

        <!-- Leverage slider -->
        <div class="tp-slider-row">
          <div class="tp-slider-header">
            <span class="tp-slider-label">Leverage (Isolated)</span>
            <span class="tp-slider-value" id="tp-lev-val-${tokenId}" style="color:#f59e0b">${leverageVal}x</span>
          </div>
          <input type="range" class="tp-slider tp-slider-lev" id="prot-lev-${tokenId}"
                 min="1" max="15" step="1" value="${leverageVal}"
                 oninput="onTradingPanelChange('${tokenId}')" />
          <div class="tp-slider-range-labels"><span>1x</span><span>15x max</span></div>

          <!-- Margin calculator box -->
          <div class="tp-margin-box" id="tp-margin-box-${tokenId}">
            <div class="tp-margin-row">
              <span>Margen requerido:</span>
              <span id="tp-mb-req-${tokenId}">—</span>
            </div>
            <div class="tp-margin-row">
              <span>Balance wallet:</span>
              <span id="tp-mb-bal-${tokenId}">cargando…</span>
            </div>
            <div class="tp-margin-row tp-margin-row--available" id="tp-mb-avail-row-${tokenId}">
              <span>Disponible después:</span>
              <span id="tp-mb-avail-${tokenId}">—</span>
            </div>
            <div class="tp-margin-row" id="tp-mb-minpool-row-${tokenId}" style="border-top:1px solid #374151;margin-top:4px;padding-top:4px;">
              <span style="color:#9ca3af;font-size:0.78rem;">Pool mínimo para cubrir:</span>
              <span id="tp-mb-minpool-${tokenId}" style="font-size:0.78rem;font-weight:600;">—</span>
            </div>
            <div class="tp-margin-note">Auto-ajustado. Siempre isolated.</div>
          </div>
        </div>

        <!-- Stop Loss Fijo -->
        <div class="prot-field">
          <label class="prot-label prot-label--danger">Stop Loss Fijo (%) <span style="color:#f87171">*</span></label>
          <div class="prot-input-group">
            <input type="number" class="prot-input" id="prot-sl-${tokenId}"
                   value="${slVal}" step="0.01" min="0.01" max="10"
                   oninput="onTradingPanelChange('${tokenId}')" />
            <span class="prot-input-suffix">%</span>
          </div>
          <span style="font-size:0.6rem;color:var(--color-text-muted);margin-top:2px">
            Cierra la posición si pierde este % desde la entrada
          </span>
        </div>

        <!-- Trailing Stop checkbox -->
        <div class="tp-check-row">
          <input type="checkbox" id="prot-trail-${tokenId}" ${trailVal ? 'checked' : ''}
                 onchange="onTradingPanelChange('${tokenId}')" />
          <label class="tp-check-label" for="prot-trail-${tokenId}">Trailing Stop</label>
        </div>

        <!-- Take Profit (optional) -->
        <div class="prot-field">
          <label class="prot-label">Take Profit (%) <span style="color:var(--color-text-muted);font-size:0.55rem">opcional</span></label>
          <div class="prot-input-group">
            <input type="number" class="prot-input" id="prot-tp-${tokenId}"
                   value="${tpVal}" step="0.1" min="0.1" placeholder="—"
                   oninput="onTradingPanelChange('${tokenId}')" />
            <span class="prot-input-suffix">%</span>
          </div>
        </div>

        <!-- Auto-rearm checkbox -->
        <div class="tp-check-row" style="margin-bottom:12px">
          <input type="checkbox" id="prot-rearm-${tokenId}" ${rearmVal ? 'checked' : ''} />
          <label class="tp-check-label" for="prot-rearm-${tokenId}">Auto-rearm</label>
          <span class="tp-check-hint">Tras SL, el bot vuelve a buscar breakouts</span>
        </div>

        <button class="btn btn-primary btn-sm prot-btn-full"
                id="prot-activate-btn-${tokenId}"
                onclick="activateProtection('${tokenId}')">
          🛡&nbsp; ${t('prot.btn.activate')}
        </button>
      </div>`;

    // Kick off async HL balance fetch and capital estimate after render (ETH pools only)
    if (!isBTC) setTimeout(() => initTradingPanel(tokenId, pos), 0);
  }

  const isActive = bot?.active;
  return `
    <div class="pc-protection">
      <button class="pc-prot-toggle ${isActive ? 'pc-prot-toggle--active' : ''}"
              onclick="toggleProtectionDrawer('${tokenId}')">
        <span class="prot-chevron ${isOpen ? 'prot-chevron--open' : ''}"
              id="prot-chevron-${tokenId}">▶</span>
        <span class="prot-toggle-label">${isActive ? '' : '⚠ '}${t('prot.drawer.title')}</span>
        ${badge}
      </button>
      <div class="pc-prot-body ${isOpen ? '' : 'hidden'}" id="prot-body-${tokenId}">
        ${bodyHtml}
      </div>
    </div>`;
}

// ── Drawer toggle ─────────────────────────────────────────────────────────

window.toggleProtectionDrawer = function (tokenId) {
  const body    = document.getElementById('prot-body-' + tokenId);
  const chevron = document.getElementById('prot-chevron-' + tokenId);
  if (!body) return;
  const opening = body.classList.contains('hidden');
  if (opening) {
    _drawerOpen.add(tokenId);
    body.classList.remove('hidden');
    chevron?.classList.add('prot-chevron--open');
  } else {
    _drawerOpen.delete(tokenId);
    body.classList.add('hidden');
    chevron?.classList.remove('prot-chevron--open');
  }
};

// ── Mode radio styling ────────────────────────────────────────────────────

window.onModeChange = function (tokenId, radio) {
  const form = document.getElementById('prot-form-' + tokenId);
  if (!form) return;
  form.querySelectorAll('.prot-mode-opt').forEach(label => {
    const input = label.querySelector('input[type="radio"]');
    label.classList.toggle('prot-mode-opt--active', !!input?.checked);
  });
};

// ── Wallet dropdown handler ───────────────────────────────────────────────
window.onWalletSelectChange = function (tokenId) {
  const sel     = document.getElementById(`prot-wallet-select-${tokenId}`);
  const input   = document.getElementById(`prot-wallet-${tokenId}`);
  const apkeyEl = document.getElementById(`prot-apikey-${tokenId}`);
  if (!sel || !input) return;
  if (sel.value) {
    // Known wallet selected — sync hidden input, keep API key hint
    input.value = sel.value;
    input.style.display = 'none';
    if (apkeyEl) apkeyEl.placeholder = t('prot.apikey.keepcurrent');
  } else {
    // "＋ Nueva dirección" selected — show text input for manual entry
    input.value = '';
    input.style.display = '';
    input.focus();
    if (apkeyEl) apkeyEl.placeholder = t('prot.apikey.placeholder');
  }
  // Show/hide remove button based on whether a saved wallet is selected
  const removeBtn = document.getElementById(`prot-wallet-remove-${tokenId}`);
  if (removeBtn) removeBtn.style.display = sel.value ? '' : 'none';

  // Re-fetch balance for the newly selected wallet and update margin box
  const selectedWallet = sel.value || null;
  _hlBalanceCache = null;
  const pos = state.positions?.find(p => String(p.tokenId) === String(tokenId));
  if (pos) fetchHLBalance(selectedWallet).then(data => {
    if (data) _hlBalanceCache = data;
    _updateMarginBox(tokenId, pos);
  });
};

window.removeHLWallet = async function (tokenId, sel) {
  const wallet = sel.value;
  if (!wallet) return;
  const short = wallet.slice(0,8) + '…' + wallet.slice(-6);
  if (!confirm(`¿Eliminar wallet HL ${short} de tus configuraciones?\n\nSi tienes bots activos con esta wallet, detenerlos primero.`)) return;
  try {
    await apiCall('DELETE', `/bots/hl-wallet?wallet=${encodeURIComponent(wallet)}`);
    // Remove option from dropdown
    const opt = [...sel.options].find(o => o.value === wallet);
    if (opt) opt.remove();
    // If no saved wallets left, show new address input
    const hasSaved = [...sel.options].some(o => o.value);
    if (!hasSaved) {
      const row    = sel.parentNode;
      const input  = document.getElementById(`prot-wallet-${tokenId}`);
      if (input) { input.value = ''; input.style.display = ''; }
      row.replaceWith(input);
    } else {
      sel.value = sel.options[0].value;
      window.onWalletSelectChange(tokenId);
    }
  } catch (e) {
    alert(`Error al eliminar wallet: ${e.message}`);
  }
};

// ── Activate bot ──────────────────────────────────────────────────────────

window.activateProtection = async function (tokenId) {
  const t   = window.t || (k => k);
  const btn = document.getElementById(`prot-activate-btn-${tokenId}`);
  if (btn) { btn.disabled = true; btn.textContent = t('prot.btn.activating'); }

  try {
    const mode         = document.querySelector(`input[name="prot-mode-${tokenId}"]:checked`)?.value || 'aragan';
    const triggerRaw   = parseFloat(document.getElementById(`prot-trigger-${tokenId}`)?.value || '0.5');
    const trigger      = -Math.abs(triggerRaw);   // stored as negative pct
    const hedge        = parseFloat(document.getElementById(`prot-hedge-${tokenId}`)?.value  || '50');
    const leverage     = parseInt(document.getElementById(`prot-lev-${tokenId}`)?.value       || '10', 10);
    const slPct        = parseFloat(document.getElementById(`prot-sl-${tokenId}`)?.value      || '0.1');
    const tpRaw        = document.getElementById(`prot-tp-${tokenId}`)?.value.trim();
    const tpPct        = tpRaw ? parseFloat(tpRaw) : null;
    const trailingStop = document.getElementById(`prot-trail-${tokenId}`)?.checked ?? true;
    const autoRearm    = document.getElementById(`prot-rearm-${tokenId}`)?.checked ?? true;
    const apiKey       = document.getElementById(`prot-apikey-${tokenId}`)?.value.trim();
    const hlWallet     = document.getElementById(`prot-wallet-${tokenId}`)?.value.trim();

    const existingBot = saas.bots[tokenId];

    // Validate: need API key on first create, optional on update
    if (!existingBot && !apiKey) {
      showError(t('prot.no.hlkey'));
      return;
    }
    if (!hlWallet) {
      showError(t('prot.no.hlkey'));
      return;
    }

    // Validate key length — must be 32 bytes (64 hex chars + optional 0x)
    if (apiKey) {
      const hexPart = apiKey.startsWith('0x') ? apiKey.slice(2) : apiKey;
      if (hexPart.length !== 64) {
        showError(`HL API Key must be 64 hex characters (32 bytes). You entered ${hexPart.length} chars. This is the PRIVATE KEY of the API Wallet, not the wallet address.`);
        if (btn) { btn.disabled = false; btn.innerHTML = `🛡&nbsp; ${t('prot.btn.activate')}`; }
        return;
      }
    }

    const pos = state.positions.find(p => p.tokenId === tokenId);
    if (!pos) throw new Error('Position not found in current state');

    let configId;

    if (existingBot) {
      // Update existing config
      const payload = {
        trigger_pct: trigger, hedge_ratio: hedge, hl_wallet_addr: hlWallet, mode,
        leverage, sl_pct: slPct, tp_pct: tpPct, trailing_stop: trailingStop, auto_rearm: autoRearm,
      };
      if (apiKey) payload.hl_api_key = apiKey;
      await apiCall('PUT', `/bots/${existingBot.id}`, payload);
      configId = existingBot.id;
    } else {
      // Create new bot config
      const pair = `${pos.token0Info.symbol}/${pos.token1Info.symbol}`;
      const res  = await apiCall('POST', '/bots', {
        chain_id:       state.chainId,
        nft_token_id:   tokenId,
        pair,
        lower_bound:    pos.priceLower,
        upper_bound:    pos.priceUpper,
        trigger_pct:    trigger,
        hedge_ratio:    hedge,
        hl_api_key:     apiKey,
        hl_wallet_addr: hlWallet,
        mode,
        leverage,
        sl_pct:         slPct,
        tp_pct:         tpPct,
        trailing_stop:  trailingStop,
        auto_rearm:     autoRearm,
      });
      configId = res.id;
    }

    // Start the bot
    _hlBalanceCache = null; // invalidate balance cache after config change
    await apiCall('POST', `/bots/${configId}/start`);

    // Refresh bot list and re-render
    await saasLoadBots();
    renderPositions();

    // Connect WebSocket for live updates
    connectBotWS(configId);

  } catch (err) {
    showError('Activation failed: ' + (err.message || err));
    if (btn) {
      btn.disabled  = false;
      btn.innerHTML = `🛡&nbsp; ${(window.t || (k=>k))('prot.btn.activate')}`;
    }
  }
};

// ── Trading Panel helpers ──────────────────────────────────────────────────

// x_max_eth: max ETH position holds when price is at lower bound (worst-case IL)
function calcXMaxEth(liquidity, tickLower, tickUpper) {
  const L    = Number(liquidity) / 1e18;
  const sqrtA = Math.sqrt(Math.pow(1.0001, tickLower));
  const sqrtB = Math.sqrt(Math.pow(1.0001, tickUpper));
  if (sqrtA === 0 || sqrtB === 0) return 0;
  return L * (1 / sqrtA - 1 / sqrtB);
}

// Cache for HL balance so we don't hammer the API on every slider move
let _hlBalanceCache = null;
let _hlBalanceFetching = false;

async function fetchHLBalance(walletAddr) {
  if (!walletAddr && _hlBalanceFetching) return _hlBalanceCache;
  if (!walletAddr && _hlBalanceCache !== null) return _hlBalanceCache;
  if (!saas.jwt) return null;
  _hlBalanceFetching = true;
  try {
    const url  = walletAddr ? `/bots/hl-balance?wallet=${encodeURIComponent(walletAddr)}` : '/bots/hl-balance';
    const data = await apiCall('GET', url);
    if (!walletAddr) _hlBalanceCache = data;
    return data;
  } catch (_) {
    return null;
  } finally {
    _hlBalanceFetching = false;
  }
}

// Called once after the trading panel is injected into DOM
async function initTradingPanel(tokenId, pos) {
  const t = window.t || (k => k);
  // Inject or refresh wallet dropdown from current saas.bots
  const walletInput  = document.getElementById(`prot-wallet-${tokenId}`);
  const existingSel  = document.getElementById(`prot-wallet-select-${tokenId}`);
  const knownWallets = [...new Set(
    Object.values(saas.bots)
      .map(b => b.hl_wallet_addr)
      .filter(w => w && w.length > 0)
  )];

  if (walletInput && knownWallets.length > 0) {
    const currentVal = existingSel ? existingSel.value : walletInput.value;
    const preselect  = currentVal || knownWallets[0];
    const options    = knownWallets.map(w =>
      `<option value="${w}" ${w === preselect ? 'selected' : ''}>${w.slice(0,8)}…${w.slice(-6)}</option>`
    ).join('');
    const optionsHtml = `${options}<option value="">＋ ${t('prot.wallet.new')}</option>`;

    if (existingSel) {
      // Dropdown already in DOM — just refresh options, preserve current selection
      existingSel.innerHTML = optionsHtml;
      existingSel.value = knownWallets.includes(currentVal) ? currentVal : preselect;
      walletInput.value = existingSel.value;
      const removeBtn = document.getElementById(`prot-wallet-remove-${tokenId}`);
      if (removeBtn) removeBtn.style.display = existingSel.value ? '' : 'none';
    } else {
      // First render — build dropdown and inject into DOM
      const sel = document.createElement('select');
      sel.className = 'prot-input prot-wallet-select';
      sel.id        = `prot-wallet-select-${tokenId}`;
      sel.innerHTML = optionsHtml;
      sel.onchange  = () => window.onWalletSelectChange(tokenId);

      const removeBtn = document.createElement('button');
      removeBtn.type        = 'button';
      removeBtn.id          = `prot-wallet-remove-${tokenId}`;
      removeBtn.className   = 'prot-wallet-remove-btn';
      removeBtn.title       = 'Eliminar wallet HL';
      removeBtn.textContent = '🗑️';
      removeBtn.style.display = preselect ? '' : 'none';
      removeBtn.onclick = () => window.removeHLWallet(tokenId, sel);

      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:6px;align-items:center;width:100%';
      row.appendChild(sel);
      row.appendChild(removeBtn);
      walletInput.parentNode.insertBefore(row, walletInput);
      walletInput.value         = preselect;
      walletInput.style.display = 'none';
    }
  }

  // Compute capital estimate from current pool value (not theoretical xMax)
  const { amount0, amount1 } = computePositionAmounts(
    pos.sqrtPriceX96, pos.tickLower, pos.tickUpper, pos.liquidity,
    pos.token0Info.decimals, pos.token1Info.decimals
  );
  const usd0 = tokenToUsd(pos.token0Info.symbol, amount0);
  const usd1 = tokenToUsd(pos.token1Info.symbol, amount1);
  const poolValueUsd = (usd0 !== null && usd1 !== null) ? usd0 + usd1 : 0;
  const hedgeEl = document.getElementById(`prot-hedge-${tokenId}`);
  const hedgeRatio = hedgeEl ? parseFloat(hedgeEl.value) / 100 : 0.5;
  const capital = poolValueUsd * hedgeRatio;

  const capEl = document.getElementById(`tp-capital-${tokenId}`);
  if (capEl) capEl.textContent = capital > 0 ? `$${capital.toFixed(2)}` : '—';

  // Fetch HL balance and update margin box
  const hlData = await fetchHLBalance();
  _updateMarginBox(tokenId, pos);
}

function _updateMarginBox(tokenId, pos) {
  const levEl   = document.getElementById(`prot-lev-${tokenId}`);
  const hedgeEl = document.getElementById(`prot-hedge-${tokenId}`);
  if (!levEl || !hedgeEl) return;

  const leverage   = parseInt(levEl.value, 10);
  const hedgeRatio = parseFloat(hedgeEl.value) / 100;
  const price      = pos.priceCurrent || 0;
  const { amount0: a0, amount1: a1 } = computePositionAmounts(
    pos.sqrtPriceX96, pos.tickLower, pos.tickUpper, pos.liquidity,
    pos.token0Info.decimals, pos.token1Info.decimals
  );
  const u0 = tokenToUsd(pos.token0Info.symbol, a0);
  const u1 = tokenToUsd(pos.token1Info.symbol, a1);
  const poolUsd  = (u0 !== null && u1 !== null) ? u0 + u1 : 0;
  const notional = poolUsd * hedgeRatio;
  const reqMargin  = notional > 0 && leverage > 0 ? notional / leverage : 0;

  const reqEl   = document.getElementById(`tp-mb-req-${tokenId}`);
  const balEl   = document.getElementById(`tp-mb-bal-${tokenId}`);
  const availEl = document.getElementById(`tp-mb-avail-${tokenId}`);
  const rowEl   = document.getElementById(`tp-mb-avail-row-${tokenId}`);
  const capEl   = document.getElementById(`tp-capital-${tokenId}`);
  const subEl   = document.getElementById(`tp-hedge-sub-${tokenId}`);

  const HL_MIN_NOTIONAL = 10;
  const tooSmall = notional > 0 && notional < HL_MIN_NOTIONAL;
  if (capEl) {
    capEl.textContent = notional > 0 ? `$${notional.toFixed(2)}` : '—';
    capEl.style.color = tooSmall ? '#ef4444' : '';
  }
  if (reqEl)  reqEl.textContent  = reqMargin > 0 ? `$${reqMargin.toFixed(2)}` : '—';

  // Warning: LP too small for HL minimum order
  let warnEl = document.getElementById(`tp-min-notional-warn-${tokenId}`);
  if (!warnEl && capEl) {
    warnEl = document.createElement('div');
    warnEl.id = `tp-min-notional-warn-${tokenId}`;
    warnEl.style.cssText = 'color:#ef4444;font-size:0.75rem;margin-top:4px;';
    capEl.parentElement.appendChild(warnEl);
  }
  if (warnEl) {
    warnEl.textContent = tooSmall
      ? `⚠️ Below HL minimum ($${HL_MIN_NOTIONAL}). Add more liquidity to enable protection.`
      : '';
  }

  // Live hedge sub-label: show actual ETH and USD amounts
  if (subEl) {
    const hedgeEth = price > 0 ? (notional / price) : 0;
    if (hedgeEth > 0 && price > 0) {
      subEl.textContent = `≈ ${hedgeEth.toFixed(4)} ETH  ≈  $${notional.toFixed(2)} al precio actual`;
      subEl.classList.remove('tp-hedge-sublabel--empty');
    } else {
      subEl.textContent = 'calculando…';
      subEl.classList.add('tp-hedge-sublabel--empty');
    }
  }

  const bal = _hlBalanceCache?.account_value;
  if (balEl) {
    balEl.textContent = bal != null ? `$${Number(bal).toFixed(2)}` : '—';
  }
  // M2-4: also update the prominent balance bar at top of modal
  const hlBarValEl = document.getElementById(`prot-hl-bal-val-${tokenId}`);
  if (hlBarValEl) {
    hlBarValEl.textContent = bal != null ? `$${Number(bal).toFixed(2)}` : '—';
  }
  if (availEl && rowEl) {
    if (bal != null && reqMargin > 0) {
      const avail = bal - reqMargin;
      availEl.textContent = `$${avail.toFixed(2)}`;
      rowEl.classList.toggle('tp-margin-row--warn', avail < 0);
      rowEl.classList.toggle('tp-margin-row--available', avail >= 0);
    } else {
      availEl.textContent = '—';
    }
  }

  // Min pool calculator: minimum pool value so hedge notional >= $10
  const minPoolEl = document.getElementById(`tp-mb-minpool-${tokenId}`);
  if (minPoolEl) {
    if (hedgeRatio > 0) {
      const minPool = HL_MIN_NOTIONAL / hedgeRatio;
      const poolOk  = poolUsd >= minPool;
      minPoolEl.textContent = `$${minPool.toFixed(2)}`;
      minPoolEl.style.color = poolOk ? '#34d399' : '#ef4444';
    } else {
      minPoolEl.textContent = '—';
      minPoolEl.style.color = '';
    }
  }
}

// Called by oninput on any trading panel control
window.onTradingPanelChange = function (tokenId) {
  // Update displayed slider labels
  const lev  = document.getElementById(`prot-lev-${tokenId}`);
  const buf  = document.getElementById(`prot-trigger-${tokenId}`);
  const hdg  = document.getElementById(`prot-hedge-${tokenId}`);

  const levValEl = document.getElementById(`tp-lev-val-${tokenId}`);
  const bufValEl = document.getElementById(`tp-buf-val-${tokenId}`);
  const hdgValEl = document.getElementById(`tp-hedge-val-${tokenId}`);

  if (lev && levValEl) levValEl.textContent = `${lev.value}x`;
  if (buf && bufValEl) bufValEl.textContent = `${parseFloat(buf.value).toFixed(1)}%`;
  if (hdg && hdgValEl) {
    const hVal = parseInt(hdg.value, 10);
    const isOffensive = hVal > 100;
    hdgValEl.textContent = isOffensive ? `${hVal}% ⚡` : `${hVal}%`;
    hdgValEl.style.color = isOffensive ? '#f59e0b' : '';
    hdg.classList.toggle('tp-slider--offensive', isOffensive);
    const warnEl = document.getElementById(`tp-offensive-warn-${tokenId}`);
    if (warnEl) {
      warnEl.textContent = isOffensive
        ? `⚡ Modo Ofensivo — short mayor que la LP. Ganas en bajadas más allá del IL, pero asumes riesgo direccional. No es cobertura pura.`
        : '';
      warnEl.classList.toggle('hidden', !isOffensive);
    }
  }

  // Recalculate margin box using cached pos from state
  const pos = state.positions?.find(p => p.tokenId === tokenId);
  if (pos) _updateMarginBox(tokenId, pos);

  // Check if user deviated from safe defaults
  checkDeviationAdvisory(tokenId);
};

// Deviation thresholds vs bot defaults
const DEVIATION_THRESHOLDS = { leverage: 12, sl_pct: 1.0 };

function checkDeviationAdvisory(tokenId) {
  const lev   = parseInt(document.getElementById(`prot-lev-${tokenId}`)?.value  || '10', 10);
  const sl    = parseFloat(document.getElementById(`prot-sl-${tokenId}`)?.value  || '0.1');
  const tp    = document.getElementById(`prot-tp-${tokenId}`)?.value.trim();
  const trail = document.getElementById(`prot-trail-${tokenId}`)?.checked ?? true;

  const deviated = lev > DEVIATION_THRESHOLDS.leverage
    || sl > DEVIATION_THRESHOLDS.sl_pct
    || (tp && !trail);    // fixed TP with trailing off

  const existing = document.getElementById('deviation-advisory');
  if (deviated && !existing) {
    showDeviationAdvisory(tokenId);
  } else if (!deviated && existing) {
    existing.remove();
  }
}

function showDeviationAdvisory(tokenId) {
  if (document.getElementById('deviation-advisory')) return;
  const el = document.createElement('div');
  el.className = 'deviation-advisory';
  el.id = 'deviation-advisory';
  el.innerHTML = `
    <div class="deviation-advisory-title">⚠ Custom Parameters Detected</div>
    <div class="deviation-advisory-body">
      You've changed settings from the bot's calibrated defaults.
      High leverage (&gt;12x) or wide SL (&gt;1%) may behave unexpectedly
      in volatile conditions.
    </div>
    <div class="deviation-advisory-actions">
      <button onclick="resetTradingPanelDefaults('${tokenId}')">Keep Defaults</button>
      <button onclick="document.getElementById('deviation-advisory')?.remove()">I Understand</button>
    </div>`;
  document.body.appendChild(el);
}

window.resetTradingPanelDefaults = function (tokenId) {
  const lev  = document.getElementById(`prot-lev-${tokenId}`);
  const sl   = document.getElementById(`prot-sl-${tokenId}`);
  const tp   = document.getElementById(`prot-tp-${tokenId}`);
  const trail = document.getElementById(`prot-trail-${tokenId}`);
  if (lev)  { lev.value   = '10'; }
  if (sl)   { sl.value    = '0.1'; }
  if (tp)   { tp.value    = ''; }
  if (trail){ trail.checked = true; }
  onTradingPanelChange(tokenId);
  document.getElementById('deviation-advisory')?.remove();
};

// ── Telegram link helpers ─────────────────────────────────────────────────

async function loadTgLinkStatus() {
  if (!saas.jwt) return;
  try {
    const data = await apiCall('GET', '/telegram/link-status');
    saas.tgLinked = data.linked ? { count: data.count } : false;
    // Refresh wallet dropdown if it's open
    const menu = document.getElementById('wallet-dropdown-menu');
    if (menu && menu.style.display !== 'none') renderWalletDropdown();
  } catch { /* silent — non-critical */ }
}

window.copyTgCmd = function (el) {
  const cmd = el.dataset.cmd || el.textContent.trim();
  navigator.clipboard.writeText(cmd).then(() => {
    const hint = el.nextElementSibling;
    if (hint) { hint.textContent = '✓ Copied!'; setTimeout(() => { hint.textContent = 'Tap to copy'; }, 2000); }
  }).catch(() => {
    // Fallback: select text
    const range = document.createRange();
    range.selectNodeContents(el);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  });
};

// Maintenance banner — checked once on dashboard load
async function checkMaintenanceStatus() {
  try {
    const res = await fetch(API_BASE + '/status/maintenance', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    const banner = document.getElementById('maintenance-banner');
    if (!banner) return;
    if (data.maintenance) {
      const msgEl = document.getElementById('maintenance-msg');
      if (msgEl && data.message) msgEl.textContent = data.message;
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  } catch (_) { /* ignore network errors for optional banner */ }
}

// ══════════════════════════════════════════════════════════════════════════════
// WHALE TRACKER — moved to /whale/ page
// ══════════════════════════════════════════════════════════════════════════════

function renderWhaleSection() {
  // Whale Tracker has moved to the dedicated /whale/ page.
}

// ── Stop bot — confirmation modal with live HL position re-query ───────────

let _stopConfirmState = { configId: null, tokenId: null };

window.stopProtection = async function (configId, tokenId) {
  // Store for use after confirmation
  _stopConfirmState = { configId, tokenId };

  const modal      = document.getElementById('stop-confirm-modal');
  const loading    = document.getElementById('stop-confirm-loading');
  const posEl      = document.getElementById('stop-confirm-position');
  const bodyEl     = document.getElementById('stop-confirm-body');
  const noPosEl    = document.getElementById('stop-confirm-no-position');
  const okBtn      = document.getElementById('stop-confirm-ok');

  // Reset modal to loading state
  loading.classList.remove('hidden');
  posEl.classList.add('hidden');
  bodyEl.classList.add('hidden');
  noPosEl.classList.add('hidden');
  okBtn.disabled = false;
  modal.classList.remove('hidden');

  // Query live HL position
  let pos = null;
  try {
    pos = await apiCall('GET', `/bots/${configId}/hl-position`);
  } catch (_) { /* show modal anyway — let user decide */ }

  loading.classList.add('hidden');

  if (pos && pos.has_position) {
    const pnl     = pos.unrealized_pnl || 0;
    const pnlCls  = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
    const pnlSign = pnl >= 0 ? '+' : '';
    posEl.innerHTML = `
      <div class="pos-row">
        <span class="pos-label">Par</span>
        <span class="pos-value">${pos.coin}/USDC — ${pos.side}</span>
      </div>
      <div class="pos-row">
        <span class="pos-label">Tamaño</span>
        <span class="pos-value">${pos.size.toFixed(4)} ${pos.coin}</span>
      </div>
      <div class="pos-row">
        <span class="pos-label">Precio entrada</span>
        <span class="pos-value">$${pos.entry_px.toFixed(2)}</span>
      </div>
      <div class="pos-row">
        <span class="pos-label">Precio actual</span>
        <span class="pos-value">$${pos.mark_px.toFixed(2)}</span>
      </div>
      <div class="pos-row">
        <span class="pos-label">PnL no realizado</span>
        <span class="pos-value ${pnlCls}">${pnlSign}$${pnl.toFixed(4)}</span>
      </div>
      <div class="pos-row">
        <span class="pos-label">Balance wallet HL</span>
        <span class="pos-value">$${(pos.account_value || 0).toFixed(2)}</span>
      </div>`;
    posEl.classList.remove('hidden');
    document.getElementById('stop-confirm-coin').textContent = pos.coin;
    bodyEl.classList.remove('hidden');
  } else {
    noPosEl.classList.remove('hidden');
  }
};

window.closeStopConfirmModal = function () {
  document.getElementById('stop-confirm-modal').classList.add('hidden');
  _stopConfirmState = { configId: null, tokenId: null };
};

window.confirmStopProtection = async function () {
  const { configId, tokenId } = _stopConfirmState;
  if (!configId) return;

  const t      = window.t || (k => k);
  const okBtn  = document.getElementById('stop-confirm-ok');
  const btn    = document.getElementById(`prot-stop-btn-${configId}`);
  okBtn.disabled = true;
  okBtn.textContent = t('prot.btn.stopping');
  if (btn) { btn.disabled = true; btn.textContent = t('prot.btn.stopping'); }

  try {
    await apiCall('POST', `/bots/${configId}/stop`);

    closeStopConfirmModal();

    // Close WebSocket
    const ws = saas.sockets[configId];
    if (ws) { try { ws.close(); } catch (_) {} delete saas.sockets[configId]; }

    await saasLoadBots();
    renderPositions();

  } catch (err) {
    showError('Stop failed: ' + (err.message || err));
    okBtn.disabled = false;
    okBtn.textContent = 'Sí, desactivar y cerrar';
    if (btn) { btn.disabled = false; btn.textContent = t('prot.btn.stop'); }
  }
};
