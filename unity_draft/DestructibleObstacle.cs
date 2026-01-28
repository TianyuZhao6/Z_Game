using UnityEngine;
using ZGame.UnityDraft.Systems;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Simple destructible obstacle. On destroy, removes itself from GridManager.
    /// </summary>
    [RequireComponent(typeof(Collider2D))]
    public class DestructibleObstacle : MonoBehaviour
    {
        public int hp = 30;
        public bool crushable = true;
        public GridManager gridManager;
        public GameObject destroyVfx;
        public AudioClip destroySfx;
        public ZGame.UnityDraft.VFX.VfxPlayer vfxPlayer;
        public ZGame.UnityDraft.VFX.SfxPlayer sfxPlayer;
        [Header("Drops")]
        public GameObject coinPrefab;
        public int coinMin = 0;
        public int coinMax = 0;
        public GameObject itemDropPrefab;
        public float dropChance = 0.2f;

        public void Damage(int amount)
        {
            hp = Mathf.Max(0, hp - Mathf.Max(0, amount));
            if (hp <= 0)
            {
                Remove();
            }
        }

        public void Crush()
        {
            Remove();
        }

        public void Remove()
        {
            if (gridManager == null) gridManager = FindObjectOfType<GridManager>();
            if (gridManager != null) gridManager.RemoveObstacle(transform.position);
            if (vfxPlayer != null && destroyVfx != null)
            {
                vfxPlayer.Play(destroyVfx.name, transform.position);
            }
            else if (destroyVfx != null)
            {
                var v = Instantiate(destroyVfx, transform.position, Quaternion.identity);
                v.SetActive(true);
            }
            if (sfxPlayer != null && destroySfx != null)
            {
                sfxPlayer.Play(destroySfx.name, transform.position);
            }
            else if (destroySfx != null)
            {
                AudioSource.PlayClipAtPoint(destroySfx, transform.position);
            }
            TryDrop();
            gameObject.SetActive(false);
        }

        private void TryDrop()
        {
            if (coinPrefab != null && (coinMin > 0 || coinMax > 0))
            {
                int amt = Random.Range(coinMin, coinMax + 1);
                for (int i = 0; i < amt; i++)
                {
                    Instantiate(coinPrefab, transform.position + (Vector3)Random.insideUnitCircle * 0.2f, Quaternion.identity);
                }
            }
            if (itemDropPrefab != null && Random.value < dropChance)
            {
                Instantiate(itemDropPrefab, transform.position, Quaternion.identity);
            }
        }

        private void OnCollisionEnter2D(Collision2D collision)
        {
            // Example crushing: if a heavy object hits, destroy
            if (crushable && collision.relativeVelocity.magnitude > 8f)
            {
                Remove();
            }
        }
    }
}
