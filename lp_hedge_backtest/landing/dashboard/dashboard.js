/**
 * VIZNAGO FURY — LP Pool Dashboard
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
  whaleSignals:   {},      // config_id → array of last N whale signal events (mode='whale' bots)
};
const WHALE_SIGNAL_MAX = 50; // max signals to keep in memory per whale bot
const LOG_MAX = 50;

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
  state.watchMode = false;
  state.activeTab = 'active';
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
  renderPositions();
};

// ── Watch Address (read-only) ─────────────────────────────────────────────

window.startWatchMode = async function () {
  const input   = document.getElementById('watch-addr-input');
  const rawAddr = (input?.value || '').trim();
  if (!rawAddr) return;

  if (!ethers.isAddress(rawAddr)) {
    showError(window.t ? window.t('dash.watch.invalid') : 'Invalid address');
    return;
  }

  const addr    = ethers.getAddress(rawAddr); // normalise to checksum form
  const chainId = parseInt(document.getElementById('watch-chain-select').value, 10);
  if (!CHAINS[chainId]) return;

  // Disable Watch button while probing RPCs
  const watchBtn  = document.querySelector('.watch-card .btn');
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

  // Restore button before navigating away from connect prompt
  if (watchBtn)  { watchBtn.disabled = false; watchBtn.style.opacity = ''; }
  if (watchSpan) { watchSpan.textContent = window.t ? window.t('dash.watch.btn') : 'Watch'; }

  state.watchMode = true;
  state.address   = addr;
  state.chainId   = chainId;
  state.provider  = provider;

  hide('connect-prompt');
  show('dashboard-content');
  updateWalletBar();
  updateChainPills();

  fetchLivePrices();
  fetchPositions();

  applyRefreshInterval();
  renderRefreshControl();
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
        uniquePools.get(key).slot0 = { sqrtPriceX96: slot0[0], tick: Number(slot0[1]) };
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

  // Navbar wallet button → shows address (eye prefix in watch mode)
  const btn = document.getElementById('wallet-btn');
  btn.textContent = (state.watchMode ? '👁 ' : '● ') + truncateAddr(state.address);
  btn.onclick = disconnectWallet;

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
}

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
      <div class="pc-status ${statusClass}">
        <span class="status-dot ${dotClass}"></span>
        ${statusLabel}
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

    <div class="pc-fees">
      <div class="pc-fees-label">${t('pos.fees.label')}${feesValueUsd !== null && feesValueUsd > 0 ? ` <span style="color:#34d399;font-size:0.72rem">≈ $${feesValueUsd.toFixed(2)}</span>` : ''}</div>
      <div class="pc-fees-values">
        ${hasFees
          ? `${fee0Display}<span>${token0Info.symbol}</span>&nbsp;+&nbsp;${fee1Display}<span>${token1Info.symbol}</span>`
          : '<span style="color:var(--color-text-muted)">—</span>'}
      </div>
    </div>

    ${buildProtectionDrawer(pos)}
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

  // Enter key on watch address input
  const watchInput = document.getElementById('watch-addr-input');
  if (watchInput) {
    watchInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') startWatchMode();
    });
  }

  // Start price ticker even before wallet connects
  fetchLivePrices();

  // Load public whale signals — no wallet required
  loadPublicWhaleSignals();

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
    const message = `Sign in to VIZNAGO FURY\nNonce: ${nonce}`;
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
        // Seed log terminal with recent DB events so it isn't blank on load
        apiCall('GET', `/bots/${bot.id}/events?limit=10`).then(events => {
          if (!Array.isArray(events) || !events.length) return;
          if (!saas.logs[bot.id]) saas.logs[bot.id] = [];
          // Events come newest-first — reverse to show oldest at top
          [...events].reverse().forEach(ev => {
            const ts  = new Date(ev.ts).toLocaleTimeString();
            const pnl = ev.pnl != null ? ` | P&L: ${ev.pnl >= 0 ? '+' : ''}$${Number(ev.pnl).toFixed(2)}` : '';
            const px  = ev.price_at_event ? ` | $${Number(ev.price_at_event).toLocaleString('en-US',{maximumFractionDigits:2})}` : '';
            saas.logs[bot.id].push(`[${ts}] ${ev.event_type.toUpperCase()}${px}${pnl}`);
          });
          renderLiveBots();
        }).catch(() => {});
        // Seed whale signals from API for whale-mode bots
        if (bot.mode === 'whale') {
          apiCall('GET', `/bots/${bot.id}/whale-signals?limit=20`).then(signals => {
            if (!Array.isArray(signals) || !signals.length) return;
            saas.whaleSignals[bot.id] = signals;
            renderLiveBots();
          }).catch(() => {});
        }
        if (!saas.sockets[bot.id]) connectBotWS(bot.id);
      }
    }
    // Re-render positions, live bots panel, and whale section
    if (state.positions.length > 0) renderPositions();
    renderLiveBots();
    renderWhaleSection();
  } catch (err) {
    // Silently ignore — JWT may be expired (apiCall handles 401)
    console.warn('[SaaS] loadBots:', err.message);
  }
}

// ── Public whale signal loader (no auth required) ────────────────────────

async function loadPublicWhaleSignals() {
  try {
    const signals = await fetch(API_BASE + '/bots/public-whale-signals?limit=50')
      .then(r => r.ok ? r.json() : []);
    if (!Array.isArray(signals) || !signals.length) return;
    // Store under a reserved key so renderWhaleSection can pick them up
    saas.whaleSignals['__public__'] = signals;
    renderWhaleSection();
  } catch (_) {}
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
            <div class="section-label">VIZNAGO FURY</div>
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

    // ── WHALE mode panel ──────────────────────────────────────────────────
    if (bot.mode === 'whale') {
      const isPaper   = bot.paper_trade === true;
      const wsMode    = bot.whale_use_websocket || false;
      const topN      = bot.whale_top_n || 50;
      const minNotional = (bot.whale_min_notional || 50000).toLocaleString();
      const assets    = bot.whale_watch_assets || 'All assets';
      const modeTag   = wsMode
        ? `<span class="status-live-tag" style="background:#00d4ff;color:#000">WS LIVE</span>`
        : `<span class="status-live-tag" style="background:#3d6b8c;color:#e8f4ff">POLL</span>`;
      const paperTag  = isPaper
        ? `<span class="status-live-tag" style="background:#f59e0b;color:#000">PAPER</span>` : '';

      const lastSignals = (saas.whaleSignals[bot.id] || []).slice(0, 5);
      const signalRows  = lastSignals.length
        ? lastSignals.map(s => {
            const d   = s.details || s;
            const dir = (d.side || s.side) === 'LONG'
              ? `<span style="color:#00ffb3">▲ LONG</span>`
              : (d.side || s.side) === 'SHORT'
                ? `<span style="color:#ff6b6b">▼ SHORT</span>`
                : `<span style="color:#7aaccc">—</span>`;
            const evt      = (s.event_type || '').replace('whale_','').replace(/_/g,' ').toUpperCase();
            const sizeUsd  = Number(d.size_usd  || s.size_usd  || 0);
            const entryPx  = Number(d.entry_px  || 0);
            const liqPx    = Number(d.liq_px    || 0);
            const lev      = d.leverage    || '—';
            const levType  = d.leverage_type ? d.leverage_type.toUpperCase() : '';
            const margin   = Number(d.margin_used    || 0);
            const roe      = Number(d.roe_pct        || 0);
            const funding  = Number(d.funding_since_open || 0);
            const rank     = d.rank;
            const addr     = d.address || '';
            const deltaUsd = Number(d.delta_usd || 0);
            const levHtml  = lev !== '—'
              ? `<span class="whale-sig-lev">${lev}x${levType ? ' <span class="whale-sig-levtype">'+levType+'</span>' : ''}</span>`
              : '';
            const liqHtml  = liqPx
              ? `<span class="whale-sig-liq" title="Liq price">Liq $${liqPx.toLocaleString(undefined,{maximumFractionDigits:2})}</span>`
              : '';
            const marginHtml = margin
              ? `<span class="whale-sig-margin" title="Margin used">Mrg $${margin.toLocaleString(undefined,{maximumFractionDigits:0})}</span>`
              : '';
            const roeHtml  = roe
              ? `<span class="whale-sig-roe ${roe>=0?'whale-sig-roe--pos':'whale-sig-roe--neg'}" title="ROE">ROE ${roe>=0?'+':''}${roe.toFixed(1)}%</span>`
              : '';
            const fundingHtml = funding
              ? `<span class="whale-sig-funding" title="Funding since open" style="color:${funding>=0?'#00ffb3':'#ff6b6b'};font-size:0.6rem">Δf ${funding>=0?'+':''}$${Math.abs(funding).toFixed(0)}</span>`
              : '';
            const rankHtml = rank != null
              ? `<span class="whale-sig-rank" title="Leaderboard rank">#${rank}</span>`
              : '';
            const addrHtml = addr
              ? `<span class="whale-sig-addr" title="${addr}" onclick="navigator.clipboard.writeText('${addr}')" style="cursor:pointer">${addr.slice(0,6)}…${addr.slice(-4)}</span>`
              : '';
            const deltaHtml = deltaUsd && Math.abs(deltaUsd) > 0
              ? `<span class="whale-sig-delta" title="Position size change" style="color:${deltaUsd>=0?'#00ffb3':'#ff6b6b'};font-size:0.6rem">${deltaUsd>=0?'▲':'▼'}$${Math.abs(deltaUsd).toLocaleString(undefined,{maximumFractionDigits:0})}</span>`
              : '';
            return `<div class="whale-signal-row">
              <div class="whale-sig-top">
                ${rankHtml}
                <span class="whale-sig-evt">${evt}</span>
                <span class="whale-sig-asset">${d.asset || s.asset || '—'}</span>
                ${dir}
                <span class="whale-sig-size">$${sizeUsd.toLocaleString(undefined,{maximumFractionDigits:0})}</span>
                ${deltaHtml}
                ${entryPx ? `<span class="whale-sig-entry" title="Entry">@ $${entryPx.toLocaleString(undefined,{maximumFractionDigits:2})}</span>` : ''}
                <span class="whale-sig-time">${s.ts ? new Date(s.ts.replace('+00:00','Z').replace(/\+\d{2}:\d{2}$/,'Z')).toLocaleTimeString() : ''}</span>
              </div>
              <div class="whale-sig-meta">
                ${levHtml}${liqHtml}${marginHtml}${roeHtml}${fundingHtml}${addrHtml}
              </div>
            </div>`;
          }).join('')
        : `<div style="color:#3d6b8c;font-size:0.75rem;padding:8px 0">${t('whale.no.signals')}</div>`;

      return `
        <div class="hedge-panel" style="margin-top:16px" id="whale-panel-${bot.id}">
          <div class="hedge-panel-header">
            <div class="section-label">VIZNAGO WHALE</div>
            <h3 class="hedge-panel-title">
              Whale Tracker ${modeTag}${paperTag}
            </h3>
          </div>
          <div class="hedge-info-grid">
            <div class="hedge-info-card">
              <div class="hi-label">${t('whale.leaderboard.label')}</div>
              <div class="hi-value text-neon">Top ${topN}</div>
              <div class="hi-sub">HL Leaderboard</div>
            </div>
            <div class="hedge-info-card">
              <div class="hi-label">${t('whale.notional.label')}</div>
              <div class="hi-value">$${minNotional}</div>
              <div class="hi-sub">${t('whale.notional.sub')}</div>
            </div>
            <div class="hedge-info-card">
              <div class="hi-label">${t('whale.assets.label')}</div>
              <div class="hi-value" style="font-size:0.8rem">${assets}</div>
              <div class="hi-sub">${t('whale.mode.label')}: ${wsMode ? 'WebSocket' : 'Poll'}</div>
            </div>
            <div class="hedge-info-card">
              <div class="hi-label">${t('whale.last.signal')}</div>
              <div id="live-bot-evt-${bot.id}" style="font-size:0.7rem">
                ${lastEvt ? `${(lastEvt.event||'').replace(/whale_/,'').replace(/_/g,' ').toUpperCase()} · ${lastEvt.price ? formatPrice(lastEvt.price) : '—'}` : t('prot.status.checking')}
              </div>
            </div>
          </div>
          <div class="whale-signals-panel">
            <div class="bot-log-header" style="display:flex;justify-content:space-between;align-items:center">
              <span>
                <span class="bot-log-title">&#128011; WHALE SIGNALS</span>
                <span class="bot-log-dot"></span>
              </span>
              <button class="btn btn-sm" style="border-color:rgba(255,100,100,0.35);color:#ff6b6b;font-size:0.68rem;padding:2px 10px"
                      onclick="stopWhaleBot(${bot.id})">⏹ Stop</button>
            </div>
            <div class="whale-signals-list" id="whale-signals-${bot.id}">${signalRows}</div>
          </div>
          ${buildLogTerminal(bot.id)}
        </div>`;
    }
    // ─────────────────────────────────────────────────────────────────────

    const modeName  = bot.mode === 'aragan'
      ? t('dash.hedge.mode.val')
      : 'Defensor Alcista (Cobertura + Long)';
    const triggerPx = (bot.lower_bound * (1 + bot.trigger_pct / 100)).toFixed(2);
    const rangePct  = (((bot.upper_bound - bot.lower_bound) / bot.lower_bound) * 100).toFixed(1);
    const chainName = { 42161: 'Arbitrum', 1: 'Ethereum', 8453: 'Base' }[bot.chain_id] || `Chain ${bot.chain_id}`;

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
            <div class="hi-label">${t('dash.hedge.trig.label')}</div>
            <div class="hi-value text-neon">$${Number(triggerPx).toLocaleString('en-US',{maximumFractionDigits:2})}</div>
            <div class="hi-sub">${bot.trigger_pct}% ${t('dash.hedge.trig.below')}</div>
          </div>
          <div class="hedge-info-card">
            <div class="hi-label">${t('dash.hedge.mode.label')}</div>
            <div class="hi-value" style="font-size:0.75rem">${modeName}</div>
            ${lastEvtHtml}
          </div>
        </div>
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
    </div>
    <div class="bot-log-terminal" id="bot-log-${configId}">${lines}</div>`;
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
        // Raw stdout line — append to log buffer and update terminal
        if (!saas.logs[configId]) saas.logs[configId] = [];
        saas.logs[configId].push(data.msg);
        if (saas.logs[configId].length > LOG_MAX) saas.logs[configId].shift();
        appendLogLine(configId, data.msg);
      } else {
        // Structured event
        saas.statuses[configId] = data;
        // Whale signals: buffer and update live feed panel
        const evt = data.event || data.event_type || '';
        if (evt.startsWith('whale_') && evt !== 'whale_snapshot') {
          if (!saas.whaleSignals[configId]) saas.whaleSignals[configId] = [];
          saas.whaleSignals[configId].unshift(data);
          if (saas.whaleSignals[configId].length > WHALE_SIGNAL_MAX)
            saas.whaleSignals[configId].pop();
          updateWhaleSignalDisplay(configId, data);
        }
        updateBotStatusDisplay(configId, data);
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

function updateWhaleSignalDisplay(configId, data) {
  const list = document.getElementById(`whale-signals-${configId}`);
  if (!list) return;

  const evt     = (data.event || data.event_type || '').replace('whale_','').replace(/_/g,' ').toUpperCase();
  const d       = data.details || {};
  const side    = d.side    || data.side    || '—';
  const asset   = d.asset   || data.asset   || '—';
  const sizeUsd = Number(d.size_usd         || data.size_usd || 0);
  const entryPx = Number(d.entry_px         || 0);
  const liqPx   = Number(d.liq_px           || 0);
  const lev     = d.leverage                || null;
  const levType = d.leverage_type           || '';
  const margin  = Number(d.margin_used      || 0);
  const roe     = Number(d.roe_pct          || 0);
  const funding = Number(d.funding_since_open || 0);
  const ts      = data.ts ? new Date(data.ts).toLocaleTimeString() : '';

  const dirHtml = side === 'LONG'
    ? `<span style="color:#00ffb3">▲ LONG</span>`
    : side === 'SHORT'
      ? `<span style="color:#ff6b6b">▼ SHORT</span>`
      : `<span style="color:#7aaccc">—</span>`;

  const levHtml    = lev ? `<span class="whale-sig-lev">${lev}x${levType ? ' <span class="whale-sig-levtype">'+levType.toUpperCase()+'</span>' : ''}</span>` : '';
  const liqHtml    = liqPx ? `<span class="whale-sig-liq" title="Liq price">Liq $${liqPx.toLocaleString(undefined,{maximumFractionDigits:2})}</span>` : '';
  const marginHtml = margin ? `<span class="whale-sig-margin" title="Margin used">Mrg $${margin.toLocaleString(undefined,{maximumFractionDigits:0})}</span>` : '';
  const roeHtml    = roe ? `<span class="whale-sig-roe ${roe>=0?'whale-sig-roe--pos':'whale-sig-roe--neg'}" title="ROE">ROE ${roe>=0?'+':''}${roe.toFixed(1)}%</span>` : '';
  const fundingHtml = funding ? `<span class="whale-sig-funding" title="Funding since open" style="color:${funding>=0?'#00ffb3':'#ff6b6b'};font-size:0.6rem">Δf ${funding>=0?'+':''}$${Math.abs(funding).toFixed(0)}</span>` : '';

  const row = document.createElement('div');
  row.className = 'whale-signal-row whale-signal-row--new';
  row.innerHTML = `
    <div class="whale-sig-top">
      <span class="whale-sig-evt">${evt}</span>
      <span class="whale-sig-asset">${asset}</span>
      ${dirHtml}
      <span class="whale-sig-size">$${sizeUsd.toLocaleString(undefined,{maximumFractionDigits:0})}</span>
      ${entryPx ? `<span class="whale-sig-entry" title="Entry">@ $${entryPx.toLocaleString(undefined,{maximumFractionDigits:2})}</span>` : ''}
      <span class="whale-sig-time">${ts}</span>
    </div>
    <div class="whale-sig-meta">${levHtml}${liqHtml}${marginHtml}${roeHtml}${fundingHtml}</div>`;

  list.insertBefore(row, list.firstChild);
  setTimeout(() => row.classList.remove('whale-signal-row--new'), 800);
  while (list.children.length > WHALE_SIGNAL_MAX) list.removeChild(list.lastChild);
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

  if (state.watchMode) {
    // Watch mode — no protection available
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

    bodyHtml = `
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

    bodyHtml = `
      ${isBTC ? `<p class="prot-btc-warning">⚠&nbsp; ${t('prot.btc.warning')}</p>` : ''}
      <div class="prot-form" id="prot-form-${tokenId}">

        <!-- Header: pair + range -->
        <div class="tp-header">
          <div class="tp-pair">${pair}</div>
          <div class="tp-range">Range ${range}</div>
        </div>

        <!-- Mode toggle -->
        <div class="prot-field" style="margin-bottom:10px">
          <label class="prot-label">${t('prot.mode.label')}</label>
          <div class="prot-mode-toggle">
            <label class="prot-mode-opt ${modeVal === 'aragan' ? 'prot-mode-opt--active' : ''}">
              <input type="radio" name="prot-mode-${tokenId}" value="aragan"
                     ${modeVal === 'aragan' ? 'checked' : ''}
                     onchange="onModeChange('${tokenId}', this)" />
              ${t('prot.mode.aragan')}
            </label>
            <label class="prot-mode-opt ${!isBTC && modeVal === 'avaro' ? 'prot-mode-opt--active' : ''} ${isBTC ? 'prot-mode-opt--disabled' : ''}">
              <input type="radio" name="prot-mode-${tokenId}" value="avaro"
                     ${!isBTC && modeVal === 'avaro' ? 'checked' : ''}
                     ${isBTC ? 'disabled' : ''}
                     onchange="onModeChange('${tokenId}', this)" />
              ${t('prot.mode.avaro')}
            </label>
          </div>
        </div>

        <!-- Capital por Operación -->
        <div class="tp-capital-row">
          <span class="tp-capital-label">Capital por Operación</span>
          <span>
            <span class="tp-capital-value" id="tp-capital-${tokenId}">—</span>
            <span class="tp-capital-hint"> = hedge notional</span>
          </span>
        </div>

        <!-- Buffer de Breakout (trigger offset slider) -->
        <div class="tp-slider-row">
          <div class="tp-slider-header">
            <span class="tp-slider-label">Buffer de Breakout
              <span class="tp-info-anchor" tabindex="0" aria-label="Qué es esto">❓
                <span class="tp-info-popover">
                  <strong>¿Cuándo dispara el bot?</strong><br><br>
                  Cuando el precio cae este % por debajo del <em>piso</em> de tu rango LP, el bot abre la cobertura SHORT automáticamente.<br><br>
                  <span style="color:#00d4ff">Ej: Piso $2,030 · -0.5% → SHORT se abre en $2,020</span><br><br>
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
                  <span style="color:#00d4ff">100%</span> → cobertura total, mayor margen requerido.
                </span>
              </span>
            </span>
            <span class="tp-slider-value" id="tp-hedge-val-${tokenId}">${hedgeVal}%</span>
          </div>
          <input type="range" class="tp-slider" id="prot-hedge-${tokenId}"
                 min="10" max="100" step="5" value="${hedgeVal}"
                 oninput="onTradingPanelChange('${tokenId}')" />
          <div class="tp-slider-range-labels"><span>10%</span><span>100%</span></div>
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

        <!-- HL Credentials -->
        <div class="prot-field">
          <label class="prot-label prot-label--danger">${t('prot.apikey.label')}</label>
          <input type="password" class="prot-input prot-input-full"
                 id="prot-apikey-${tokenId}" placeholder="${apiKeyPH}" autocomplete="off" />
        </div>
        <div class="prot-field" style="margin-bottom:4px">
          <label class="prot-label prot-label--warning">${t('prot.wallet.label')}</label>
          <input type="text" class="prot-input prot-input-full"
                 id="prot-wallet-${tokenId}" value="${hlWallet}"
                 placeholder="${t('prot.wallet.placeholder')}" />
        </div>

        <button class="btn btn-primary btn-sm prot-btn-full"
                id="prot-activate-btn-${tokenId}"
                onclick="activateProtection('${tokenId}')">
          🛡&nbsp; ${t('prot.btn.activate')}
        </button>
      </div>`;

    // Kick off async HL balance fetch and capital estimate after render
    setTimeout(() => initTradingPanel(tokenId, pos), 0);
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

async function fetchHLBalance() {
  if (_hlBalanceFetching) return _hlBalanceCache;
  if (_hlBalanceCache !== null) return _hlBalanceCache;
  if (!saas.jwt) return null;
  _hlBalanceFetching = true;
  try {
    const data = await apiCall('GET', '/bots/hl-balance');
    _hlBalanceCache = data;
    return data;
  } catch (_) {
    return null;
  } finally {
    _hlBalanceFetching = false;
  }
}

// Called once after the trading panel is injected into DOM
async function initTradingPanel(tokenId, pos) {
  // Compute capital estimate
  const xMax    = calcXMaxEth(pos.liquidity, pos.tickLower, pos.tickUpper);
  const hedgeEl = document.getElementById(`prot-hedge-${tokenId}`);
  const hedgeRatio = hedgeEl ? parseFloat(hedgeEl.value) / 100 : 0.5;
  const price   = pos.priceCurrent || 0;
  const capital = xMax * hedgeRatio * price;

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
  const xMax       = calcXMaxEth(pos.liquidity, pos.tickLower, pos.tickUpper);
  const notional   = xMax * hedgeRatio * price;
  const reqMargin  = notional > 0 && leverage > 0 ? notional / leverage : 0;

  const reqEl   = document.getElementById(`tp-mb-req-${tokenId}`);
  const balEl   = document.getElementById(`tp-mb-bal-${tokenId}`);
  const availEl = document.getElementById(`tp-mb-avail-${tokenId}`);
  const rowEl   = document.getElementById(`tp-mb-avail-row-${tokenId}`);
  const capEl   = document.getElementById(`tp-capital-${tokenId}`);
  const subEl   = document.getElementById(`tp-hedge-sub-${tokenId}`);

  if (capEl)  capEl.textContent  = notional > 0 ? `$${notional.toFixed(2)}` : '—';
  if (reqEl)  reqEl.textContent  = reqMargin > 0 ? `$${reqMargin.toFixed(2)}` : '—';

  // Live hedge sub-label: show actual ETH and USD amounts
  if (subEl) {
    const hedgeEth = xMax * hedgeRatio;
    if (hedgeEth > 0 && price > 0) {
      subEl.textContent = `≈ ${hedgeEth.toFixed(4)} ETH  ≈  $${(hedgeEth * price).toFixed(2)} al precio actual`;
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
  if (hdg && hdgValEl) hdgValEl.textContent = `${hdg.value}%`;

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
// WHALE TRACKER SECTION
// Standalone section — no LP position required.
// Renders running whale bots + a form to launch a new one.
// ══════════════════════════════════════════════════════════════════════════════

function renderWhaleSection() {
  const section = document.getElementById('whale-section');
  if (!section) return;
  const t = window.t || (k => k);

  const whaleBots = Object.values(saas.bots).filter(b => b.mode === 'whale');

  // Running panels (already rendered via renderLiveBots for active bots,
  // but we also want stopped ones visible here with a restart option)
  const stoppedBots = whaleBots.filter(b => !b.active);

  const stoppedCards = stoppedBots.map(bot => `
    <div class="hedge-panel" style="margin-top:12px;opacity:0.7">
      <div class="hedge-panel-header">
        <div class="section-label" style="color:#3d6b8c">VIZNAGO WHALE · STOPPED</div>
        <h3 class="hedge-panel-title" style="font-size:0.85rem">
          Top-${bot.whale_top_n || 50} · $${Number(bot.whale_min_notional||50000).toLocaleString()} min
          <span class="badge badge--muted" style="margin-left:8px">ID ${bot.id}</span>
        </h3>
      </div>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn btn-sm" style="border-color:rgba(0,212,255,0.4);color:#00d4ff"
                onclick="restartWhaleBot(${bot.id})">▶ Restart</button>
        <button class="btn btn-sm" style="border-color:rgba(255,100,100,0.3);color:#ff6b6b"
                onclick="deleteWhaleBot(${bot.id})">🗑 Delete</button>
      </div>
    </div>`).join('');

  section.innerHTML = `
    <div class="hedge-panel" style="margin-top:24px;border-color:rgba(0,212,255,0.2)">
      <div class="hedge-panel-header">
        <div class="section-label" style="color:#00d4ff">🐋 WHALE TRACKER</div>
        <h3 class="hedge-panel-title">
          Monitor Top Traders &amp; Copy Signals
        </h3>
      </div>

      <p style="font-size:0.78rem;color:var(--color-text-secondary);margin:0 0 16px">
        Tracks Hyperliquid leaderboard addresses in real-time. Detects large position opens,
        closes, side flips, and size changes. Signals appear live in the panel above when a
        whale bot is running.
      </p>

      ${(() => {
        // Aggregate signals: prefer live websocket data, fall back to public endpoint
        const allSignals = [
          ...Object.entries(saas.whaleSignals)
            .filter(([k]) => k !== '__public__')
            .flatMap(([, s]) => s),
          ...(saas.whaleSignals['__public__'] || []),
        ].filter((s, i, arr) => {
          // deduplicate by ts+asset+event_type
          const key = `${s.ts}|${s.asset}|${s.event_type}`;
          return arr.findIndex(x => `${x.ts}|${x.asset}|${x.event_type}` === key) === i;
        }).sort((a, b) => (b.ts > a.ts ? 1 : -1)).slice(0, 20);

        if (!allSignals.length) return `
          <p style="font-size:0.75rem;color:var(--color-text-secondary);margin:0 0 16px;text-align:center;opacity:0.6">
            No signals yet — whale tracker is polling…
          </p>`;

        const evColor = t => ({ whale_new_position:'#00d4ff', whale_closed:'#9ca3af',
          whale_flip:'#f59e0b', whale_size_increase:'#34d399', whale_size_decrease:'#f87171' }[t] || '#9ca3af');
        const evLabel = t => t.replace('whale_','').replace(/_/g,' ').toUpperCase();

        const rows = allSignals.map(s => {
          const side  = (s.side||'').toUpperCase();
          const sideColor = side === 'LONG' ? '#34d399' : side === 'SHORT' ? '#f87171' : '#9ca3af';
          const sz    = s.size_usd ? `$${Number(s.size_usd).toLocaleString('en-US',{maximumFractionDigits:0})}` : '—';
          const delta = s.delta_usd != null
            ? `<span style="color:${s.delta_usd>=0?'#34d399':'#f87171'}">${s.delta_usd>=0?'▲':'▼'}$${Math.abs(Number(s.delta_usd)).toLocaleString('en-US',{maximumFractionDigits:0})}</span>` : '';
          const addr  = s.address ? `<span title="${s.address}" style="cursor:pointer;font-size:0.68rem;color:#6b7280" onclick="navigator.clipboard?.writeText('${s.address}')">${s.address.slice(0,6)}…${s.address.slice(-4)}</span>` : '';
          const ts    = (() => { try { return new Date(s.ts.replace(/[+-]\d{2}:\d{2}$/,'')).toLocaleTimeString(); } catch(_){return s.ts||'';} })();
          return `<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
            <td style="padding:5px 6px;font-size:0.7rem;color:#6b7280;white-space:nowrap">${ts}</td>
            <td style="padding:5px 6px;font-size:0.72rem;font-weight:600;color:${evColor(s.event_type)}">${evLabel(s.event_type)}</td>
            <td style="padding:5px 6px;font-size:0.72rem;font-weight:600">${s.asset||'—'}</td>
            <td style="padding:5px 6px;font-size:0.72rem;color:${sideColor}">${side||'—'}</td>
            <td style="padding:5px 6px;font-size:0.72rem;text-align:right">${sz}</td>
            <td style="padding:5px 6px;font-size:0.72rem;text-align:right">${delta}</td>
            <td style="padding:5px 6px">${addr}</td>
          </tr>`;
        }).join('');

        return `<div style="overflow-x:auto;margin-bottom:16px">
          <table style="width:100%;border-collapse:collapse;font-size:0.72rem">
            <thead><tr style="border-bottom:1px solid rgba(255,255,255,0.1)">
              <th style="padding:4px 6px;text-align:left;color:#6b7280;font-weight:500;font-size:0.68rem">TIME</th>
              <th style="padding:4px 6px;text-align:left;color:#6b7280;font-weight:500;font-size:0.68rem">EVENT</th>
              <th style="padding:4px 6px;text-align:left;color:#6b7280;font-weight:500;font-size:0.68rem">ASSET</th>
              <th style="padding:4px 6px;text-align:left;color:#6b7280;font-weight:500;font-size:0.68rem">SIDE</th>
              <th style="padding:4px 6px;text-align:right;color:#6b7280;font-weight:500;font-size:0.68rem">SIZE</th>
              <th style="padding:4px 6px;text-align:right;color:#6b7280;font-weight:500;font-size:0.68rem">DELTA</th>
              <th style="padding:4px 6px;color:#6b7280;font-weight:500;font-size:0.68rem">WHALE</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
      })()}

      ${saas.jwt ? stoppedCards : ''}

      <!-- Launch form — requires wallet auth -->
      ${saas.jwt ? `<div id="whale-launch-form" class="prot-form" style="margin-top:${stoppedBots.length ? '20px' : '0'}">` : `
      <div id="whale-launch-form" class="prot-form" style="margin-top:0;opacity:0.5;pointer-events:none;position:relative">
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:2;background:rgba(10,15,26,0.7);border-radius:8px">
          <span style="font-size:0.8rem;color:var(--color-text-secondary)">🔒 Connect wallet to launch a tracker</span>
        </div>
      <div>`}
        <div class="tp-header" style="margin-bottom:14px">
          <div class="tp-pair">New Whale Tracker</div>
          <div class="tp-range">Hyperliquid · Public API</div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">

          <!-- Leaderboard Top N -->
          <div class="prot-field">
            <label class="prot-label">
              Leaderboard Top N
              <span class="tp-info-anchor" tabindex="0">❓
                <span class="tp-info-popover">
                  Number of top HL leaderboard traders (ranked by PnL) to monitor.
                  <span style="color:#00d4ff">30–50 is a good balance of coverage vs API load.</span>
                </span>
              </span>
            </label>
            <input type="number" class="prot-input" id="whale-top-n"
                   min="5" max="100" step="5" value="30"
                   placeholder="30" />
          </div>

          <!-- Min Notional -->
          <div class="prot-field">
            <label class="prot-label">
              Min Notional (USD)
              <span class="tp-info-anchor" tabindex="0">❓
                <span class="tp-info-popover">
                  Only emit signals for positions above this USD size.
                  <span style="color:#00d4ff">$50K–$100K filters out small traders.</span>
                </span>
              </span>
            </label>
            <input type="number" class="prot-input" id="whale-min-notional"
                   min="10000" max="10000000" step="10000" value="100000"
                   placeholder="100000" />
          </div>

          <!-- Poll Interval -->
          <div class="prot-field">
            <label class="prot-label">Poll Interval (sec)</label>
            <input type="number" class="prot-input" id="whale-poll-interval"
                   min="10" max="300" step="5" value="30"
                   placeholder="30" />
          </div>

          <!-- Watch Assets -->
          <div class="prot-field">
            <label class="prot-label">
              Watch Assets
              <span class="tp-info-anchor" tabindex="0">❓
                <span class="tp-info-popover">
                  Comma-separated list, e.g. <strong>BTC,ETH</strong>.
                  Leave blank to track all assets.
                </span>
              </span>
            </label>
            <input type="text" class="prot-input" id="whale-watch-assets"
                   placeholder="BTC,ETH (blank = all)" />
          </div>

        </div>

        <!-- Custom addresses (full width) -->
        <div class="prot-field" style="margin-top:10px">
          <label class="prot-label">
            Custom Addresses (optional)
            <span class="tp-info-anchor" tabindex="0">❓
              <span class="tp-info-popover">
                Comma-separated 0x addresses to monitor in addition to the leaderboard.
                Useful for known whale wallets.
              </span>
            </span>
          </label>
          <input type="text" class="prot-input" id="whale-custom-addresses"
                 placeholder="0xABC..., 0xDEF... (optional)" />
        </div>

        <!-- Mode: WS vs Poll + Paper trade -->
        <div style="display:flex;gap:16px;margin-top:12px;align-items:center;flex-wrap:wrap">
          <label style="display:flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--color-text-secondary);cursor:pointer">
            <input type="checkbox" id="whale-use-ws" />
            <span>
              WebSocket mode
              <span class="tp-info-anchor" tabindex="0">❓
                <span class="tp-info-popover tp-info-popover--left">
                  <strong>WebSocket mode</strong>: ~100–500ms latency per whale fill.
                  Best for copy-trading signals.<br><br>
                  <strong>Poll mode</strong>: snapshots every N seconds. Simpler, lower resource use.
                </span>
              </span>
            </span>
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--color-text-secondary);cursor:pointer">
            <input type="checkbox" id="whale-paper-trade" checked />
            <span style="color:#f59e0b">📋 Read-only / Paper mode</span>
          </label>
        </div>

        <button class="btn btn-primary btn-sm prot-btn-full"
                style="margin-top:16px;background:linear-gradient(135deg,rgba(0,212,255,0.15),rgba(0,212,255,0.05));border-color:rgba(0,212,255,0.5);color:#00d4ff"
                id="whale-launch-btn"
                onclick="launchWhaleBot()">
          🐋&nbsp; Launch Whale Tracker
        </button>
        <p id="whale-launch-error" style="color:#ff6b6b;font-size:0.75rem;min-height:16px;margin-top:6px"></p>
      </div>

    </div>`;
}

window.launchWhaleBot = async function () {
  const btn = document.getElementById('whale-launch-btn');
  const err = document.getElementById('whale-launch-error');
  if (btn) { btn.disabled = true; btn.textContent = 'Launching…'; }
  if (err) err.textContent = '';

  try {
    const topN        = parseInt(document.getElementById('whale-top-n')?.value || '30', 10);
    const minNotional = parseFloat(document.getElementById('whale-min-notional')?.value || '100000');
    const pollInt     = parseInt(document.getElementById('whale-poll-interval')?.value || '30', 10);
    const watchAssets = document.getElementById('whale-watch-assets')?.value.trim() || '';
    const customAddrs = document.getElementById('whale-custom-addresses')?.value.trim() || '';
    const useWs       = document.getElementById('whale-use-ws')?.checked ?? false;
    const paperTrade  = document.getElementById('whale-paper-trade')?.checked ?? true;

    // Create a unique placeholder token id for this whale bot
    const tokenId = `whale-${Date.now()}`;

    const res = await apiCall('POST', '/bots', {
      mode:                    'whale',
      chain_id:                state.chainId || 42161,
      nft_token_id:            tokenId,
      pair:                    'WHALE',
      lower_bound:             0,
      upper_bound:             0,
      whale_top_n:             topN,
      whale_min_notional:      minNotional,
      whale_poll_interval:     pollInt,
      whale_watch_assets:      watchAssets,
      whale_custom_addresses:  customAddrs,
      whale_use_websocket:     useWs,
      whale_oi_spike_threshold: 0.03,
      paper_trade:             paperTrade,
    });

    const configId = res.id;

    // Start the bot
    await apiCall('POST', `/bots/${configId}/start`);

    // Reload bots + re-render
    await saasLoadBots();
    connectBotWS(configId);

  } catch (e) {
    if (err) err.textContent = 'Launch failed: ' + (e.message || e);
    if (btn) { btn.disabled = false; btn.textContent = '🐋 Launch Whale Tracker'; }
  }
};

window.restartWhaleBot = async function (configId) {
  try {
    await apiCall('POST', `/bots/${configId}/start`);
    await saasLoadBots();
    connectBotWS(configId);
  } catch (e) {
    showError('Restart failed: ' + (e.message || e));
  }
};

window.stopWhaleBot = async function (configId) {
  try {
    await apiCall('POST', `/bots/${configId}/stop`);
    await saasLoadBots();
  } catch (e) {
    showError('Stop failed: ' + (e.message || e));
  }
};

window.deleteWhaleBot = async function (configId) {
  if (!confirm('Delete this whale tracker config? This cannot be undone.')) return;
  try {
    await apiCall('DELETE', `/bots/${configId}`);
    // Remove from local state
    for (const [k, b] of Object.entries(saas.bots)) {
      if (b.id === configId) { delete saas.bots[k]; break; }
    }
    renderWhaleSection();
    renderLiveBots();
  } catch (e) {
    showError('Delete failed: ' + (e.message || e));
  }
};

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
