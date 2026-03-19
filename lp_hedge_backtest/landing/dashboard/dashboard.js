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
    rpc:         'https://arbitrum.llamarpc.com',
    nfpmAddr:    '0xC36442b4a4522E871399CD717aBDD847Ab11FE88',
    factoryAddr: '0x1F98431c8aD98523631AE4a59f267346ea31F984',
  },
  1: {
    name:        'Ethereum',
    rpc:         'https://eth.llamarpc.com',
    nfpmAddr:    '0xC36442b4a4522E871399CD717aBDD847Ab11FE88',
    factoryAddr: '0x1F98431c8aD98523631AE4a59f267346ea31F984',
  },
  8453: {
    name:        'Base',
    rpc:         'https://base.llamarpc.com',
    nfpmAddr:    '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f4',
    factoryAddr: '0x33128a8fC17869897dcE68Ed026d694621f6FDfD',
  },
};

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
  provider:  null,   // ethers.BrowserProvider (wallet)
  address:   null,   // connected wallet address
  chainId:   null,   // numeric chain id
  positions: [],     // fetched position objects
  prices:    { eth: null, btc: null },
  loading:   false,
  refreshTimer: null,
};

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
  renderConnectPrompt();
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

function onWalletConnected() {
  setWalletBtnLoading(false);
  renderWalletConnected();

  registerWalletListeners();

  // Initial data load
  fetchLivePrices();
  fetchPositions();

  // Auto-refresh every 30 s
  clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(() => {
    fetchLivePrices();
    fetchPositions();
  }, 30_000);
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
      hide('positions-loading');
      show('no-positions');
      updatePositionCount(0);
      return;
    }

    // Fetch all tokenIds in parallel
    const tokenIdPromises = [];
    for (let i = 0; i < balance; i++) {
      tokenIdPromises.push(nfpm.tokenOfOwnerByIndex(state.address, i));
    }
    const tokenIds = await Promise.all(tokenIdPromises);

    // Fetch position data for each tokenId in parallel
    const posDataPromises = tokenIds.map(id => nfpm.positions(id).then(p => ({ tokenId: id, ...p })));
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
        tokenId:     raw.tokenId.toString(),
        token0:      raw.token0,
        token1:      raw.token1,
        fee:         Number(raw.fee),
        token0Info,
        token1Info,
        tickLower,
        tickUpper,
        liquidity,
        tokensOwed0,
        tokensOwed1,
        priceLower,
        priceUpper,
        priceCurrent,
        priceBase:   priceLowerObj.base,
        priceQuote:  priceLowerObj.quote,
        rangeStatus,
        rangePercent,
      };
    });

    hide('positions-loading');
    updatePositionCount(state.positions.length);
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
    // CoinGecko free API — no key required for basic price endpoint
    const res = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=ethereum,bitcoin&vs_currencies=usd',
      { signal: AbortSignal.timeout(8000) }
    );
    if (!res.ok) throw new Error('CoinGecko HTTP ' + res.status);
    const data = await res.json();
    state.prices.eth = data?.ethereum?.usd ?? null;
    state.prices.btc = data?.bitcoin?.usd   ?? null;
  } catch (err) {
    console.warn('Price fetch failed (CoinGecko):', err.message);
    // Silently fail — ticker will show last known value
  }
  renderPriceTicker();
}

// ── Render ────────────────────────────────────────────────────────────────

function renderConnectPrompt() {
  hide('dashboard-content');
  show('connect-prompt');

  const btn = document.getElementById('wallet-btn');
  btn.textContent = '🟢 Connect Wallet';
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
  document.getElementById('ws-address').textContent = truncateAddr(state.address);
  const chainCfg = CHAINS[state.chainId];
  document.getElementById('ws-chain').textContent = chainCfg
    ? chainCfg.name
    : `Chain ID ${state.chainId} (unsupported)`;

  // Navbar wallet button → now shows address
  const btn = document.getElementById('wallet-btn');
  btn.textContent = '● ' + truncateAddr(state.address);
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

function updatePositionCount(n) {
  document.getElementById('ws-count').textContent = n + (n === 1 ? ' position' : ' positions');
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

  if (!state.positions.length) {
    show('no-positions');
    return;
  }
  hide('no-positions');

  // Sort: in-range first, then out-low, out-high, closed
  const order = { 'in-range': 0, 'out-low': 1, 'out-high': 2, 'closed': 3, 'unknown': 4 };
  const sorted = [...state.positions].sort((a, b) => (order[a.rangeStatus] ?? 4) - (order[b.rangeStatus] ?? 4));

  sorted.forEach(pos => {
    const card = buildPositionCard(pos);
    grid.appendChild(card);
  });
}

function buildPositionCard(pos) {
  const { tokenId, token0Info, token1Info, fee, priceLower, priceUpper, priceCurrent,
          priceBase, rangeStatus, rangePercent, liquidity, tokensOwed0, tokensOwed1 } = pos;

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
  const statusLabel = rangeStatus === 'in-range' ? 'IN RANGE'
                    : rangeStatus === 'out-low'   ? 'OUT ↓ BELOW'
                    : rangeStatus === 'out-high'  ? 'OUT ↑ ABOVE'
                    : rangeStatus === 'closed'    ? 'CLOSED'
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
    rangePctText = `<strong>${rangePercent.toFixed(1)}%</strong> through range`;
  } else if (rangeStatus === 'out-low') {
    rangePctText = 'Price is <strong>below</strong> lower bound — hedge active zone';
  } else if (rangeStatus === 'out-high') {
    rangePctText = 'Price is <strong>above</strong> upper bound — all in stablecoin';
  } else if (rangeStatus === 'closed') {
    rangePctText = 'Position closed (zero liquidity)';
  }

  // Fees owed display
  const fee0Display = formatTokenAmount(tokensOwed0, token0Info.decimals);
  const fee1Display = formatTokenAmount(tokensOwed1, token1Info.decimals);
  const hasFees     = tokensOwed0 > 0n || tokensOwed1 > 0n;

  card.innerHTML = `
    <div class="pc-header">
      <div>
        <div class="pc-id">NFT #${tokenId}</div>
        <div class="pc-pair">${pairLabel}</div>
        <div class="pc-fee">Fee tier: ${feeDisplay}</div>
      </div>
      <div class="pc-status ${statusClass}">
        <span class="status-dot ${dotClass}"></span>
        ${statusLabel}
      </div>
    </div>

    <div class="pc-divider"></div>

    <div class="pc-range-section">
      <div class="pc-range-label">Price Range (${priceBase})</div>
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
        <div class="pc-price-label">Lower Bound</div>
        <div class="pc-price-value lower">${formatPrice(priceLower)}</div>
      </div>
      <div class="pc-price-item">
        <div class="pc-price-label">Current Price</div>
        <div class="pc-price-value current">${priceCurrent !== null ? formatPrice(priceCurrent) : '—'}</div>
      </div>
      <div class="pc-price-item">
        <div class="pc-price-label">Upper Bound</div>
        <div class="pc-price-value upper">${formatPrice(priceUpper)}</div>
      </div>
    </div>

    ${rangePctText
      ? `<div class="pc-range-pct">${rangePctText}</div>`
      : ''}

    <div class="pc-fees">
      <div class="pc-fees-label">Fees Owed</div>
      <div class="pc-fees-values">
        ${hasFees
          ? `${fee0Display}<span>${token0Info.symbol}</span>&nbsp;+&nbsp;${fee1Display}<span>${token1Info.symbol}</span>`
          : '<span style="color:var(--color-text-muted)">—</span>'}
      </div>
    </div>
  `;

  return card;
}

// ── UI Helpers ────────────────────────────────────────────────────────────

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

function setWalletBtnLoading(loading) {
  const btn = document.getElementById('wallet-btn');
  btn.disabled  = loading;
  btn.textContent = loading ? '⏳ Connecting…' : '🟢 Connect Wallet';
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
    if (hint) hint.textContent = 'Rabby Wallet detected ✓';
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
