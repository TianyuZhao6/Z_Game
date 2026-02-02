using UnityEngine;
using System;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// High-level game state coordinator: level start/end, boss flags, twin boss toggle, bandit spawn toggle, biome buffs stub.
    /// This is a scaffold; hook up your scene/UI and level configs.
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public LevelFlow levelFlow;
        public MetaProgression meta;
        public HUDController hud;
        public UI.MenuController menu;
        public LevelSession session;
        [Header("Biome Runtime")]
        public LevelFlow.BiomeBuff currentBiome;
        public static GameManager Instance;
        public float contactDamageMult = 1f;
        public float bossContactDamageMult = 1f;
        [Header("Hurricane Prefab (Wind biome)")]
        public GameObject hurricanePrefab;
        public int hurricaneCount = 1;
        [Header("Fog Prefab (Misty biome)")]
        public GameObject fogPrefab;
        private GameObject _fogInstance;

        [Header("Runtime State")]
        public int currentLevelIndex = 0; // 0-based
        public bool bossLevel = false;
        public bool twinBoss = false;
        public bool banditAllowed = false;
        public string biome = null;

        public event Action OnLevelStarted;
        public event Action OnLevelCompleted;
        public event Action OnLevelFailed;

        private void Awake()
        {
            Instance = this;
            if (levelFlow == null) levelFlow = GetComponent<LevelFlow>();
            if (meta == null) meta = GetComponent<MetaProgression>();
            if (hud == null) hud = FindObjectOfType<HUDController>();
            if (menu == null) menu = FindObjectOfType<UI.MenuController>();
            if (session == null) session = FindObjectOfType<LevelSession>();
        }

        public void StartLevel(int levelIdx)
        {
            currentLevelIndex = levelIdx;
            bossLevel = levelFlow != null && levelFlow.IsBossLevel(levelIdx);
            twinBoss = levelFlow != null && levelFlow.UseTwinBoss(levelIdx);
            banditAllowed = levelFlow != null && levelFlow.ShouldSpawnBandit(levelIdx);
            biome = levelFlow != null ? levelFlow.NextBiome(levelIdx) : null;
            currentBiome = levelFlow?.ApplyBiomeBuffs(biome, balance);
            ApplyBiomeSideEffects();
            OnLevelStarted?.Invoke();
            menu?.HideStartSequence();
            hud?.SetTimer(session != null ? session.levelTime : 0f);
            menu?.BindMeta(meta, this);
        }

        public void CompleteLevel()
        {
            Time.timeScale = 0f;
            meta?.OnLevelComplete(currentLevelIndex);
            OnLevelCompleted?.Invoke();
            menu?.ShowSuccess();
        }

        public void FailLevel()
        {
            Time.timeScale = 0f;
            OnLevelFailed?.Invoke();
            menu?.ShowFail();
        }

        private void ApplyBiomeSideEffects()
        {
            // Wind biome: enable WindBiomeModifier components
            var windMods = FindObjectsOfType<WindBiomeModifier>(true);
            foreach (var w in windMods)
            {
                w.enabled = currentBiome != null && currentBiome.wind && currentBiome.name == w.biomeName;
            }
            // Coin multiplier for spoils
            var bcs = FindObjectOfType<Combat.BulletCombatSystem>();
            if (bcs != null && currentBiome != null)
            {
                bcs.coinMult = currentBiome.coinMult;
                // Scorched Hell: boost paint curing (use paint bonus)
                if (currentBiome.name == "Scorched Hell")
                {
                    bcs.paintBonusMult = 1.30f;
                }
            }
            // Paint color override
            var paint = FindObjectOfType<PaintSystem>();
            if (paint != null && currentBiome != null)
            {
                paint.defaultPaintColor = currentBiome.paintColor;
                // Domain of Wind hazard placeholder: spawn a breeze patch once
                if (currentBiome.wind)
                {
                    paint.SpawnEnemyPaint(transform.position, paint.hurricaneRadius, paint.hurricaneLifetime, currentBiome.paintColor);
                }
            }
            // Spawn hurricanes for wind biome
            if (currentBiome != null && currentBiome.wind && hurricanePrefab != null)
            {
                SpawnHurricanes();
            }
            // Player buffs per biome
            var player = FindObjectOfType<Player>();
            if (player != null && currentBiome != null)
            {
                player.xpGainMult = 1f;
                if (currentBiome.name == "Domain of Wind")
                {
                    player.speed = Mathf.Min(player.speed * 1.12f, player.balance != null ? player.balance.playerSpeedCap : player.speed);
                    player.xpGainMult = 1f;
                }
                else if (currentBiome.name == "Scorched Hell")
                {
                    player.attack = Mathf.RoundToInt(player.attack * 2f);
                    player.xpGainMult = 1f;
                }
                else if (currentBiome.name == "Bastion of Stone")
                {
                    player.shieldHp = Mathf.RoundToInt(player.maxHp * 0.5f);
                    player.xpGainMult = 1f;
                }
                else if (currentBiome.name == "Misty Forest")
                {
                    player.xpGainMult = 1.3f;
                }
            }
            // Contact damage multipliers
            contactDamageMult = 1f;
            bossContactDamageMult = 1f;
            if (currentBiome != null && currentBiome.name == "Scorched Hell")
            {
                contactDamageMult = 2.0f;
                bossContactDamageMult = 1.5f;
            }
            // Fog for Misty Forest
            if (currentBiome != null && currentBiome.name == "Misty Forest")
            {
                RenderSettings.fog = true;
                RenderSettings.fogColor = new Color(0.55f, 0.65f, 0.70f, 1f);
                RenderSettings.fogDensity = 0.015f;
                if (_fogInstance == null && fogPrefab != null)
                {
                    _fogInstance = Instantiate(fogPrefab);
                    var fc = _fogInstance.GetComponent<Systems.FogController>();
                    if (fc != null)
                    {
                        fc.target = FindObjectOfType<Player>()?.transform;
                        fc.cam = Camera.main;
                    }
                }
            }
            else
            {
                RenderSettings.fog = false;
                if (_fogInstance != null) Destroy(_fogInstance);
            }
            // Banner
            if (menu != null && !string.IsNullOrEmpty(biome))
            {
                menu.ShowBanner($"Entering {biome}", 1.5f);
            }
        }

        private void SpawnHurricanes()
        {
            var grid = FindObjectOfType<GridManager>();
            float cs = balance != null ? balance.cellSize : 52f;
            float mapW = (balance != null ? balance.gridSize : 32) * cs;
            float mapH = (balance != null ? balance.gridSize : 32) * cs;
            float infoH = balance != null ? balance.infoBarHeight : 40f;
            var player = FindObjectOfType<Player>();
            Vector2 pPos = player != null ? (Vector2)player.transform.position : Vector2.zero;
            float minDist = cs * 6f;
            float margin = (balance != null ? balance.cellSize * 6f : 300f) * 1.2f;
            for (int i = 0; i < hurricaneCount; i++)
            {
                Vector3 pos = new Vector3(mapW * 0.5f, infoH + mapH * 0.5f, 0f);
                for (int tries = 0; tries < 40; tries++)
                {
                    float x = Random.Range(margin, mapW - margin);
                    float y = infoH + Random.Range(margin, mapH - margin);
                    Vector2 cand = new Vector2(x, y);
                    if ((cand - pPos).sqrMagnitude >= minDist * minDist)
                    {
                        pos = new Vector3(x, y, 0f);
                        break;
                    }
                }
                var h = Instantiate(hurricanePrefab, pos, Quaternion.identity);
                var hc = h.GetComponent<Hurricane>();
                if (hc != null) hc.Init(balance, grid, pos);
            }
        }
    }
}
