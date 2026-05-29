pub fn readable_model_label(
    provider_family: Option<&str>,
    model: Option<&str>,
    display_name: Option<&str>,
) -> String {
    if let Some(display) = display_name.filter(|value| !value.trim().is_empty()) {
        if let Some(model_id) = model
            && display.contains(model_id)
        {
            return readable_model_id(provider_family, model_id);
        }
        return display.to_owned();
    }
    model
        .map(|model_id| readable_model_id(provider_family, model_id))
        .unwrap_or_else(|| "not selected".to_owned())
}

pub fn readable_model_id(provider_family: Option<&str>, model: &str) -> String {
    let model_id = strip_provider_prefix(model);
    match normalized_family(provider_family, model) {
        Some("anthropic") => readable_anthropic_model(model_id),
        Some("openai") => readable_openai_model(model_id),
        Some("gemini") => readable_gemini_model(model_id),
        Some("ollama") => prefixed_model("Ollama", model_id),
        Some("lm-studio") => prefixed_model("LM Studio", model_id),
        Some("vllm") => prefixed_model("vLLM", model_id),
        Some("local" | "chat-completions" | "chat_completions") => {
            prefixed_model("Local", model_id)
        }
        Some(family) => prefixed_model(&title_tokens(family), model_id),
        None => title_tokens(model_id),
    }
}

fn normalized_family<'a>(provider_family: Option<&'a str>, model: &'a str) -> Option<&'a str> {
    provider_family.or_else(|| model.split_once('/').map(|(family, _)| family))
}

fn readable_anthropic_model(model: &str) -> String {
    let mut tokens = drop_date_suffix(model.split('-').collect::<Vec<_>>());
    if tokens.first() == Some(&"claude") {
        tokens.remove(0);
    }
    if tokens.is_empty() {
        return "Claude".to_owned();
    }
    let family = title_token(tokens.remove(0));
    let version = version_label(&tokens);
    ["Claude".to_owned(), family, version]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn readable_openai_model(model: &str) -> String {
    if let Some(rest) = model.strip_prefix("gpt-") {
        return format!("GPT-{}", rest.to_uppercase());
    }
    title_tokens(model)
}

fn readable_gemini_model(model: &str) -> String {
    let rest = model.strip_prefix("gemini-").unwrap_or(model);
    let suffix = title_tokens(rest);
    if suffix.is_empty() {
        "Gemini".to_owned()
    } else {
        format!("Gemini {suffix}")
    }
}

fn prefixed_model(prefix: &str, model: &str) -> String {
    let readable = title_tokens(model);
    if readable.is_empty() {
        prefix.to_owned()
    } else {
        format!("{prefix} {readable}")
    }
}

fn version_label(tokens: &[&str]) -> String {
    let mut version_parts = Vec::new();
    let mut labels = Vec::new();
    for token in tokens {
        if is_numeric_token(token) {
            version_parts.push(*token);
        } else {
            labels.push(title_token(token));
        }
    }
    [version_parts.join("."), labels.join(" ")]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn title_tokens(value: &str) -> String {
    value
        .replace([':', '_'], "-")
        .split('-')
        .filter(|token| !token.is_empty())
        .map(title_token)
        .collect::<Vec<_>>()
        .join(" ")
}

fn title_token(token: &str) -> String {
    let lower = token.to_ascii_lowercase();
    if lower.starts_with("gpt") {
        return token.to_ascii_uppercase();
    }
    if lower.starts_with("llama") && lower.len() > "llama".len() {
        return format!("Llama {}", &token["llama".len()..]);
    }
    if token
        .chars()
        .all(|character| character.is_ascii_uppercase())
    {
        return token.to_owned();
    }
    let mut chars = lower.chars();
    match chars.next() {
        Some(first) => format!(
            "{}{}",
            first.to_ascii_uppercase(),
            chars.collect::<String>()
        ),
        None => String::new(),
    }
}

fn drop_date_suffix(mut tokens: Vec<&str>) -> Vec<&str> {
    if tokens
        .last()
        .is_some_and(|token| token.len() == 8 && token.chars().all(|char| char.is_ascii_digit()))
    {
        tokens.pop();
    }
    tokens
}

fn strip_provider_prefix(model: &str) -> &str {
    model
        .split_once('/')
        .map(|(_, model)| model)
        .unwrap_or(model)
}

fn is_numeric_token(token: &str) -> bool {
    !token.is_empty()
        && token
            .split('.')
            .all(|part| !part.is_empty() && part.chars().all(|char| char.is_ascii_digit()))
}

#[cfg(test)]
mod tests {
    use super::{readable_model_id, readable_model_label};

    #[test]
    fn formats_common_provider_model_ids() {
        assert_eq!(
            readable_model_id(Some("anthropic"), "claude-sonnet-4-20250514"),
            "Claude Sonnet 4"
        );
        assert_eq!(
            readable_model_id(Some("anthropic"), "claude-opus-4-7"),
            "Claude Opus 4.7"
        );
        assert_eq!(readable_model_id(Some("openai"), "gpt-5.2"), "GPT-5.2");
        assert_eq!(
            readable_model_id(Some("gemini"), "gemini-2.5-pro"),
            "Gemini 2.5 Pro"
        );
        assert_eq!(
            readable_model_id(Some("ollama"), "llama3.2"),
            "Ollama Llama 3.2"
        );
    }

    #[test]
    fn repairs_legacy_display_names_that_embed_raw_ids() {
        assert_eq!(
            readable_model_label(
                Some("anthropic"),
                Some("claude-opus-4-7"),
                Some("Anthropic Claude claude-opus-4-7"),
            ),
            "Claude Opus 4.7"
        );
        assert_eq!(
            readable_model_label(
                Some("anthropic"),
                Some("claude-opus-4-7"),
                Some("Anthropic Claude Opus 4.7"),
            ),
            "Anthropic Claude Opus 4.7"
        );
    }
}
