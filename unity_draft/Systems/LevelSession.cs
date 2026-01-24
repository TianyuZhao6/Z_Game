using UnityEngine;
using ZGame.UnityDraft.UI;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple level session coordinator: wires GameManager to MenuController and LevelFlow.
    /// Replace with your scene-specific loader as you build content.
    /// </summary>
    public class LevelSession : MonoBehaviour
    {
        public GameManager gameManager;
        public MenuController menu;
        public WaveSpawner waveSpawner;
        public ShopUI shopUI;
        [Tooltip("Open shop after success before next level.")]
        public bool openShopOnSuccess = true;
        [Tooltip("Auto-pause when shop is open.")]
        public bool pauseOnShop = true;
        [Header("Scene Navigation")]
        public string homeSceneName = "Home";
        public string levelSceneName = "Level";

        private void Awake()
        {
            if (gameManager == null) gameManager = GetComponent<GameManager>();
            if (waveSpawner == null) waveSpawner = FindObjectOfType<WaveSpawner>();
            if (menu == null) menu = FindObjectOfType<MenuController>();
            if (shopUI == null) shopUI = FindObjectOfType<ShopUI>();
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
            Time.timeScale = 1f;
            gameManager?.StartLevel(levelIdx);
            if (waveSpawner != null && gameManager != null)
            {
                waveSpawner.ConfigureForLevel(gameManager, gameManager.levelFlow);
            }
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
            if (openShopOnSuccess && shopUI != null)
            {
                shopUI.gameObject.SetActive(true);
                shopUI.Populate();
                if (pauseOnShop) Time.timeScale = 0f;
            }
        }

        private void HandleLevelFailed()
        {
            if (menu != null) menu.ShowFail();
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
    }
}
