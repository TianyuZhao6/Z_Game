using UnityEngine;
using System.Collections;
using ZGame.UnityDraft.UI;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple level session coordinator: wires GameManager to MenuController and LevelFlow.
    /// Handles start/end sequences and level-up pickers.
    /// </summary>
    public class LevelSession : MonoBehaviour
    {
        public GameManager gameManager;
        public MenuController menu;
        public WaveSpawner waveSpawner;
        public ShopUI shopUI;
        public LevelUpPicker levelUpPicker;
        public HUDController hud;
        public MetaProgression meta;
        public Player player;
        public float levelTime = 120f;
        private float _timeLeft;
        private bool _running;
        [Tooltip("Open shop after success before next level.")]
        public bool openShopOnSuccess = true;
        [Tooltip("Auto-pause when shop is open.")]
        public bool pauseOnShop = true;
        [Header("Sequences")]
        public float startSequenceDuration = 1.5f;
        public float endSequenceDuration = 1f;
        [Header("Scene Navigation")]
        public string homeSceneName = "Home";
        public string levelSceneName = "Level";

        private void Awake()
        {
            if (gameManager == null) gameManager = GetComponent<GameManager>();
            if (waveSpawner == null) waveSpawner = FindObjectOfType<WaveSpawner>();
            if (menu == null) menu = FindObjectOfType<MenuController>();
            if (shopUI == null) shopUI = FindObjectOfType<ShopUI>();
            if (levelUpPicker == null) levelUpPicker = FindObjectOfType<LevelUpPicker>();
            if (hud == null) hud = FindObjectOfType<HUDController>();
            if (meta == null) meta = FindObjectOfType<MetaProgression>();
            if (player == null) player = FindObjectOfType<Player>();
            if (waveSpawner != null && waveSpawner.enemyFactory == null)
            {
                waveSpawner.enemyFactory = FindObjectOfType<EnemyFactory>();
            }

            if (gameManager != null)
            {
                gameManager.OnLevelStarted += HandleLevelStarted;
                gameManager.OnLevelCompleted += HandleLevelCompleted;
                gameManager.OnLevelFailed += HandleLevelFailed;
            }
        }

        public void StartLevel(int levelIdx)
        {
            StartCoroutine(StartLevelRoutine(levelIdx));
        }

        private IEnumerator StartLevelRoutine(int levelIdx)
        {
            Time.timeScale = 0f;
            if (menu != null) menu.ShowStartSequence();
            float t = 0f;
            while (t < startSequenceDuration)
            {
                t += Time.unscaledDeltaTime;
                yield return null;
            }
            if (menu != null) menu.HideStartSequence();
            Time.timeScale = 1f;
            gameManager?.StartLevel(levelIdx);
            if (waveSpawner != null && gameManager != null)
            {
                waveSpawner.ConfigureForLevel(gameManager, gameManager.levelFlow);
            }
            _timeLeft = levelTime;
            _running = true;
            if (hud != null && player != null) hud.SetHp(player.hp, player.maxHp);
            if (hud != null) hud.SetCoins(meta != null ? meta.runCoins + meta.bankedCoins : 0);
            menu?.BindMeta(meta, gameManager);
        }

        private void HandleLevelStarted()
        {
            // Hook wave spawner state per level if needed
            if (waveSpawner != null)
            {
                waveSpawner.enabled = true;
            }
        }

        private void HandleLevelCompleted()
        {
            if (menu != null) menu.ShowSuccess();
            if (levelUpPicker != null) levelUpPicker.OfferLevelUp();
            if (openShopOnSuccess && shopUI != null)
            {
                shopUI.gameObject.SetActive(true);
                shopUI.Populate();
                if (pauseOnShop) Time.timeScale = 0f;
            }
            StartCoroutine(EndSequenceRoutine());
        }

        private void HandleLevelFailed()
        {
            if (menu != null) menu.ShowFail();
            StartCoroutine(EndSequenceRoutine());
        }

        public void OnRestartRequested()
        {
            if (pauseOnShop) Time.timeScale = 1f;
            if (shopUI != null) shopUI.gameObject.SetActive(false);
            // Scene reload stub
            UnityEngine.SceneManagement.SceneManager.LoadScene(levelSceneName);
        }

        public void OnHomeRequested()
        {
            if (pauseOnShop) Time.timeScale = 1f;
            if (shopUI != null) shopUI.gameObject.SetActive(false);
            if (!string.IsNullOrEmpty(homeSceneName))
            {
                UnityEngine.SceneManagement.SceneManager.LoadScene(homeSceneName);
            }
        }

        private IEnumerator EndSequenceRoutine()
        {
            Time.timeScale = 0f;
            if (menu != null) menu.ShowEndSequence();
            float t = 0f;
            while (t < endSequenceDuration)
            {
                t += Time.unscaledDeltaTime;
                yield return null;
            }
            if (menu != null) menu.HideEndSequence();
        }

        private void Update()
        {
            if (!_running) return;
            _timeLeft -= Time.deltaTime;
            if (hud != null) hud.SetTimer(_timeLeft);
            if (_timeLeft <= 0f)
            {
                _running = false;
                gameManager?.CompleteLevel();
            }
        }

        public void NotifyKill()
        {
            meta?.AddKill(1);
            hud?.SetCoins(meta != null ? meta.runCoins + meta.bankedCoins : 0);
            menu?.BindMeta(meta, gameManager);
        }

        public void NotifyCoin(int amount)
        {
            meta?.AddRunCoins(amount);
            hud?.SetCoins(meta != null ? meta.runCoins + meta.bankedCoins : 0);
            menu?.BindMeta(meta, gameManager);
        }

        public void NotifyPlayerHp()
        {
            if (hud != null && player != null) hud.SetHp(player.hp, player.maxHp);
        }
    }
}
