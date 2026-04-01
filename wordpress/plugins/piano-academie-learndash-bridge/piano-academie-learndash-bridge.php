<?php
/**
 * Plugin Name: Piano Academie LearnDash Bridge
 * Plugin URI: https://piano-academie.com
 * Description: Expose un endpoint REST pour synchroniser les cours, sections et lecons LearnDash vers Piano Academie.
 * Version: 0.1.0
 * Author: Piano Academie
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

const PIANO_ACADEMIE_LD_BRIDGE_TOKEN_OPTION = 'piano_academie_learndash_bridge_token';

function piano_academie_ld_bridge_is_learndash_available(): bool {
    return post_type_exists('sfwd-courses');
}

function piano_academie_ld_bridge_get_token(): string {
    return trim((string) get_option(PIANO_ACADEMIE_LD_BRIDGE_TOKEN_OPTION, ''));
}

function piano_academie_ld_bridge_mask_token(string $token): string {
    $trimmed = trim($token);
    if ($trimmed === '') {
        return '';
    }
    $length = strlen($trimmed);
    if ($length <= 8) {
        return str_repeat('*', $length);
    }
    return substr($trimmed, 0, 4) . str_repeat('*', $length - 8) . substr($trimmed, -4);
}

function piano_academie_ld_bridge_read_bearer_token(WP_REST_Request $request): string {
    $header = (string) $request->get_header('authorization');
    if ($header === '') {
        return '';
    }
    if (stripos($header, 'Bearer ') === 0) {
        return trim(substr($header, 7));
    }
    return trim($header);
}

function piano_academie_ld_bridge_permission(WP_REST_Request $request) {
    $configured_token = piano_academie_ld_bridge_get_token();
    if ($configured_token === '') {
        return true;
    }
    $incoming_token = piano_academie_ld_bridge_read_bearer_token($request);
    if ($incoming_token !== '' && hash_equals($configured_token, $incoming_token)) {
        return true;
    }
    return new WP_Error(
        'piano_academie_ld_bridge_forbidden',
        __('Invalid API token for Piano Academie LearnDash Bridge.', 'piano-academie-learndash-bridge'),
        array('status' => 403)
    );
}

function piano_academie_ld_bridge_meta_first(int $post_id, array $keys): ?string {
    foreach ($keys as $key) {
        $value = trim((string) get_post_meta($post_id, $key, true));
        if ($value !== '') {
            return $value;
        }
    }
    return null;
}

function piano_academie_ld_bridge_post_status_label(string $post_status): string {
    $normalized = strtoupper(trim($post_status));
    if ($normalized === 'PUBLISH') {
        return 'PUBLISHED';
    }
    if ($normalized === 'PRIVATE' || $normalized === 'DRAFT' || $normalized === 'PENDING') {
        return 'DRAFT';
    }
    if ($normalized === 'TRASH') {
        return 'ARCHIVED';
    }
    return 'PUBLISHED';
}

function piano_academie_ld_bridge_level_code(int $course_id): ?string {
    return piano_academie_ld_bridge_meta_first(
        $course_id,
        array('_piano_level_code', 'piano_level_code', 'course_level', 'niveau')
    );
}

function piano_academie_ld_bridge_summary(int $post_id): ?string {
    $excerpt = trim((string) get_post_field('post_excerpt', $post_id));
    if ($excerpt !== '') {
        return wp_strip_all_tags($excerpt);
    }
    $content = trim((string) get_post_field('post_content', $post_id));
    if ($content === '') {
        return null;
    }
    return wp_trim_words(wp_strip_all_tags($content), 28);
}

function piano_academie_ld_bridge_rendered_content(int $post_id): ?string {
    $content = (string) get_post_field('post_content', $post_id);
    if (trim($content) === '') {
        return null;
    }
    return apply_filters('the_content', $content);
}

function piano_academie_ld_bridge_video_url(int $post_id): ?string {
    return piano_academie_ld_bridge_meta_first(
        $post_id,
        array('lesson_video_url', '_lesson_video_url', 'video_url', '_video_url')
    );
}

function piano_academie_ld_bridge_resource_url(int $post_id): ?string {
    return piano_academie_ld_bridge_meta_first(
        $post_id,
        array('resource_url', '_resource_url', 'download_url', '_download_url')
    );
}

function piano_academie_ld_bridge_lesson_payload(int $post_id, int $position): array {
    $post = get_post($post_id);
    if (!$post instanceof WP_Post) {
        return array();
    }

    return array(
        'external_id' => (string) $post_id,
        'title' => get_the_title($post_id),
        'slug' => $post->post_name ?: null,
        'position' => $position,
        'summary' => piano_academie_ld_bridge_summary($post_id),
        'content_html' => piano_academie_ld_bridge_rendered_content($post_id),
        'video_url' => piano_academie_ld_bridge_video_url($post_id),
        'resource_url' => piano_academie_ld_bridge_resource_url($post_id),
        'status' => piano_academie_ld_bridge_post_status_label((string) $post->post_status),
    );
}

function piano_academie_ld_bridge_topic_ids(int $lesson_id, int $course_id): array {
    if (function_exists('learndash_get_topic_list')) {
        $topics = learndash_get_topic_list($lesson_id, $course_id);
        if (is_array($topics) && !empty($topics)) {
            return array_values(array_map(static function ($item): int {
                if ($item instanceof WP_Post) {
                    return (int) $item->ID;
                }
                if (is_array($item) && isset($item['post']) && $item['post'] instanceof WP_Post) {
                    return (int) $item['post']->ID;
                }
                return (int) $item;
            }, $topics));
        }
    }

    $query = new WP_Query(
        array(
            'post_type' => 'sfwd-topic',
            'post_status' => array('publish', 'private', 'draft'),
            'posts_per_page' => -1,
            'orderby' => array(
                'menu_order' => 'ASC',
                'title' => 'ASC',
            ),
            'meta_query' => array(
                array(
                    'key' => 'lesson_id',
                    'value' => (string) $lesson_id,
                ),
            ),
            'fields' => 'ids',
        )
    );

    return array_map('intval', $query->posts);
}

function piano_academie_ld_bridge_section_payload(int $lesson_id, int $position, int $course_id): array {
    $lesson = get_post($lesson_id);
    if (!$lesson instanceof WP_Post) {
        return array();
    }

    $topic_ids = piano_academie_ld_bridge_topic_ids($lesson_id, $course_id);
    $lessons = array();
    if (!empty($topic_ids)) {
        foreach ($topic_ids as $topic_index => $topic_id) {
            $payload = piano_academie_ld_bridge_lesson_payload((int) $topic_id, $topic_index + 1);
            if (!empty($payload)) {
                $lessons[] = $payload;
            }
        }
    } else {
        $payload = piano_academie_ld_bridge_lesson_payload($lesson_id, 1);
        if (!empty($payload)) {
            $lessons[] = $payload;
        }
    }

    return array(
        'external_id' => (string) $lesson_id,
        'title' => get_the_title($lesson_id),
        'position' => $position,
        'lessons' => $lessons,
    );
}

function piano_academie_ld_bridge_course_lessons(int $course_id): array {
    if (function_exists('learndash_course_get_steps_by_type')) {
        $lesson_ids = learndash_course_get_steps_by_type($course_id, 'sfwd-lessons');
        if (is_array($lesson_ids)) {
            return array_values(array_map('intval', $lesson_ids));
        }
    }

    if (function_exists('learndash_get_course_lessons_list')) {
        $lessons = learndash_get_course_lessons_list($course_id);
        if (is_array($lessons) && !empty($lessons)) {
            return array_values(array_filter(array_map(static function ($item): int {
                if ($item instanceof WP_Post) {
                    return (int) $item->ID;
                }
                if (is_array($item) && isset($item['post']) && $item['post'] instanceof WP_Post) {
                    return (int) $item['post']->ID;
                }
                return (int) $item;
            }, $lessons)));
        }
    }

    $query = new WP_Query(
        array(
            'post_type' => 'sfwd-lessons',
            'post_status' => array('publish', 'private', 'draft'),
            'posts_per_page' => -1,
            'orderby' => array(
                'menu_order' => 'ASC',
                'title' => 'ASC',
            ),
            'meta_query' => array(
                array(
                    'key' => 'course_id',
                    'value' => (string) $course_id,
                ),
            ),
            'fields' => 'ids',
        )
    );

    return array_map('intval', $query->posts);
}

function piano_academie_ld_bridge_course_payload(int $course_id): array {
    $post = get_post($course_id);
    if (!$post instanceof WP_Post) {
        return array();
    }

    $lesson_ids = piano_academie_ld_bridge_course_lessons($course_id);
    $sections = array();
    foreach ($lesson_ids as $index => $lesson_id) {
        $section = piano_academie_ld_bridge_section_payload($lesson_id, $index + 1, $course_id);
        if (!empty($section)) {
            $sections[] = $section;
        }
    }

    return array(
        'external_id' => (string) $course_id,
        'title' => get_the_title($course_id),
        'slug' => $post->post_name ?: null,
        'summary' => piano_academie_ld_bridge_summary($course_id),
        'level_code' => piano_academie_ld_bridge_level_code($course_id),
        'status' => piano_academie_ld_bridge_post_status_label((string) $post->post_status),
        'cover_image_url' => get_the_post_thumbnail_url($course_id, 'large') ?: null,
        'sections' => $sections,
        'lessons' => array(),
    );
}

function piano_academie_ld_bridge_catalog(): array {
    $query = new WP_Query(
        array(
            'post_type' => 'sfwd-courses',
            'post_status' => array('publish', 'private', 'draft'),
            'posts_per_page' => -1,
            'orderby' => array(
                'menu_order' => 'ASC',
                'title' => 'ASC',
            ),
            'fields' => 'ids',
        )
    );

    $courses = array();
    foreach ($query->posts as $course_id) {
        $payload = piano_academie_ld_bridge_course_payload((int) $course_id);
        if (!empty($payload)) {
            $courses[] = $payload;
        }
    }
    return $courses;
}

function piano_academie_ld_bridge_rest_catalog(WP_REST_Request $request): WP_REST_Response {
    if (!piano_academie_ld_bridge_is_learndash_available()) {
        return new WP_REST_Response(
            array(
                'courses' => array(),
                'provider' => 'WORDPRESS_LEARNDASH',
                'warning' => 'LearnDash is not active on this WordPress instance.',
            ),
            200
        );
    }

    return new WP_REST_Response(
        array(
            'provider' => 'WORDPRESS_LEARNDASH',
            'generated_at' => current_time('mysql', true),
            'courses' => piano_academie_ld_bridge_catalog(),
        ),
        200
    );
}

function piano_academie_ld_bridge_register_routes(): void {
    register_rest_route(
        'piano/v1',
        '/courses',
        array(
            'methods' => WP_REST_Server::READABLE,
            'callback' => 'piano_academie_ld_bridge_rest_catalog',
            'permission_callback' => 'piano_academie_ld_bridge_permission',
        )
    );
}
add_action('rest_api_init', 'piano_academie_ld_bridge_register_routes');

function piano_academie_ld_bridge_admin_menu(): void {
    add_options_page(
        __('Piano Academie LearnDash', 'piano-academie-learndash-bridge'),
        __('Piano Academie LearnDash', 'piano-academie-learndash-bridge'),
        'manage_options',
        'piano-academie-learndash-bridge',
        'piano_academie_ld_bridge_render_settings_page'
    );
}
add_action('admin_menu', 'piano_academie_ld_bridge_admin_menu');

function piano_academie_ld_bridge_register_settings(): void {
    register_setting(
        'piano_academie_learndash_bridge',
        PIANO_ACADEMIE_LD_BRIDGE_TOKEN_OPTION,
        array(
            'type' => 'string',
            'sanitize_callback' => static function ($value): string {
                return trim((string) $value);
            },
            'default' => '',
        )
    );
}
add_action('admin_init', 'piano_academie_ld_bridge_register_settings');

function piano_academie_ld_bridge_render_settings_page(): void {
    if (!current_user_can('manage_options')) {
        return;
    }
    $token = piano_academie_ld_bridge_get_token();
    $endpoint = rest_url('piano/v1/courses');
    ?>
    <div class="wrap">
        <h1><?php echo esc_html__('Piano Academie LearnDash Bridge', 'piano-academie-learndash-bridge'); ?></h1>
        <p><?php echo esc_html__('Expose le catalogue LearnDash pour Piano Academie via un endpoint REST JSON.', 'piano-academie-learndash-bridge'); ?></p>
        <table class="widefat striped" style="max-width: 960px; margin: 16px 0;">
            <tbody>
                <tr>
                    <th style="width: 220px;"><?php echo esc_html__('Endpoint REST', 'piano-academie-learndash-bridge'); ?></th>
                    <td><code><?php echo esc_html($endpoint); ?></code></td>
                </tr>
                <tr>
                    <th><?php echo esc_html__('Token actuel', 'piano-academie-learndash-bridge'); ?></th>
                    <td><?php echo $token === '' ? esc_html__('Aucun token configure', 'piano-academie-learndash-bridge') : esc_html(piano_academie_ld_bridge_mask_token($token)); ?></td>
                </tr>
            </tbody>
        </table>
        <form method="post" action="options.php" style="max-width: 720px;">
            <?php settings_fields('piano_academie_learndash_bridge'); ?>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row">
                        <label for="<?php echo esc_attr(PIANO_ACADEMIE_LD_BRIDGE_TOKEN_OPTION); ?>">
                            <?php echo esc_html__('Token Bearer', 'piano-academie-learndash-bridge'); ?>
                        </label>
                    </th>
                    <td>
                        <input
                            type="text"
                            class="regular-text"
                            id="<?php echo esc_attr(PIANO_ACADEMIE_LD_BRIDGE_TOKEN_OPTION); ?>"
                            name="<?php echo esc_attr(PIANO_ACADEMIE_LD_BRIDGE_TOKEN_OPTION); ?>"
                            value="<?php echo esc_attr($token); ?>"
                            autocomplete="off"
                        />
                        <p class="description">
                            <?php echo esc_html__('Si un token est defini ici, Piano Academie devra l envoyer dans Authorization: Bearer ... pour synchroniser le catalogue.', 'piano-academie-learndash-bridge'); ?>
                        </p>
                    </td>
                </tr>
            </table>
            <?php submit_button(__('Enregistrer le token', 'piano-academie-learndash-bridge')); ?>
        </form>
    </div>
    <?php
}
