using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Attach to coin/spoil pickups. Awards run coins to MetaProgression and updates HUD, then destroys or disables.
    /// </summary>
    [RequireComponent(typeof(Collider2D))]
    public class CoinPickup : MonoBehaviour
    {
        public int amount = 1;
        public MetaProgression meta;
        public HUDController hud;
        public bool destroyOnPickup = true;

        private void OnTriggerEnter2D(Collider2D other)
        {
            var player = other.GetComponentInParent<Player>();
            if (player == null) return;
            Award();
        }

        public void Award()
        {
            if (meta != null)
            {
                meta.AddRunCoins(amount);
                if (hud != null) hud.SetCoins(meta.runCoins + meta.bankedCoins);
            }
            if (destroyOnPickup)
            {
                Destroy(gameObject);
            }
            else
            {
                gameObject.SetActive(false);
            }
        }
    }
}
