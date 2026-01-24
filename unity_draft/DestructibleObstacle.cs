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
            if (destroyVfx != null)
            {
                var v = Instantiate(destroyVfx, transform.position, Quaternion.identity);
                v.SetActive(true);
            }
            if (destroySfx != null)
            {
                AudioSource.PlayClipAtPoint(destroySfx, transform.position);
            }
            gameObject.SetActive(false);
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
